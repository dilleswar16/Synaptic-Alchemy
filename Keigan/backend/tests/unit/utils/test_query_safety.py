"""keigan/utils/query_safety.py: validation and hardening of generated KQL, Elastic DSL and Splunk SPL."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from keigan.ai.prompt_library import PromptLibrary
from keigan.utils.query_safety import (
    QueryRejectedError,
    configured_splunk_index,
    describe_query_limits,
    load_query_safety_policy,
    validate_elastic_index_pattern,
    validate_elastic_query,
    validate_generated_query,
    validate_kql,
    validate_spl,
)

WINDOW_END = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - timedelta(hours=1)
# 2026-11-20 11:00 and 12:00 UTC as Unix seconds (2026-01-01 = 1767225600, + 323 days + 11 h / 12 h).
EPOCH_START, EPOCH_END = 1795172400, 1795176000


class TestValidateKql:
    def test_adds_the_investigation_time_window_after_the_source_table(self) -> None:
        hardened = validate_kql("AppRequests | where Success == false", WINDOW_START, WINDOW_END)
        assert hardened.query_text.startswith(
            "AppRequests\n| where TimeGenerated between (datetime(2026-11-20T11:00:00Z) .. datetime(2026-11-20T12:00:00Z)) | where Success == false"
        )

    def test_caps_rows_when_the_query_has_no_limit(self) -> None:
        hardened = validate_kql("AppRequests | where Success == false", WINDOW_START, WINDOW_END)
        assert hardened.query_text.endswith("| take 500")

    def test_leaves_aggregations_without_a_row_cap(self) -> None:
        hardened = validate_kql("AppRequests | summarize count() by bin(TimeGenerated, 5m)", WINDOW_START, WINDOW_END)
        assert "| take" not in hardened.query_text

    def test_a_limit_inside_a_subquery_does_not_remove_the_row_cap_of_the_main_query(self) -> None:
        hardened = validate_kql("AppRequests | join kind=inner (AppExceptions | take 5) on OperationId", WINDOW_START, WINDOW_END)
        assert hardened.query_text.endswith("| take 500")

    def test_accepts_union_join_and_lookup_of_allowed_tables(self) -> None:
        validate_kql("union AppRequests, AppExceptions | summarize count()", WINDOW_START, WINDOW_END)
        validate_kql("AppRequests | join kind=inner (AppExceptions | project OperationId) on OperationId | summarize count()", WINDOW_START, WINDOW_END)
        validate_kql("AppRequests | lookup AppExceptions on OperationId | summarize count()", WINDOW_START, WINDOW_END)
        validate_kql("AppRequests | extend x = toscalar(AppExceptions | count) | summarize count()", WINDOW_START, WINDOW_END)

    def test_accepts_a_string_that_contains_a_pipe_or_a_table_name(self) -> None:
        hardened = validate_kql('AppRequests | where Name == "SecurityEvent | union x" | summarize count()', WINDOW_START, WINDOW_END)
        assert hardened.query_text.startswith("AppRequests\n| where TimeGenerated between")

    def test_the_time_filter_goes_after_the_source_even_when_a_string_contains_a_pipe(self) -> None:
        hardened = validate_kql('AppRequests | where Name == "a|b"', WINDOW_START, WINDOW_END)
        assert hardened.query_text.startswith("AppRequests\n| where TimeGenerated between (datetime(2026-11-20T11:00:00Z)")

    @pytest.mark.parametrize(
        "query_text",
        [
            pytest.param(".show tables", id="management-command"),
            pytest.param("externaldata (x:string) [@'https://evil.example/data.csv']", id="externaldata"),
            pytest.param("AppRequests | evaluate http_request('https://evil.example')", id="http-plugin"),
            pytest.param("workspace('other-workspace').AppRequests", id="cross-workspace"),
            pytest.param("AppRequests | take 1; SecurityEvent | take 1", id="second-statement"),
            pytest.param("SecurityEvent | take 10", id="table-not-allowed"),
            pytest.param("AppRequests | join kind=inner (SecurityEvent) on Computer", id="join-table-not-allowed"),
            pytest.param("find in (*) where * has 'password'", id="find-across-all-tables"),
            pytest.param("", id="empty"),
        ],
    )
    def test_rejects_unsafe_queries(self, query_text: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_kql(query_text, WINDOW_START, WINDOW_END)

    def test_rejects_union_with_a_table_that_is_not_allowed(self) -> None:
        with pytest.raises(QueryRejectedError):
            validate_kql("AppRequests | union SecurityEvent | take 10", WINDOW_START, WINDOW_END)

    @pytest.mark.parametrize(
        "query_text",
        [
            pytest.param("AppRequests | union SecurityEvent | summarize count()", id="v4-union"),
            pytest.param("AppRequests | join kind=inner SecurityEvent on $left.AppRoleName == $right.Computer | summarize count()", id="v4-join-without-parentheses"),
            pytest.param("AppRequests | lookup SigninLogs on UserId | summarize count()", id="v4-lookup-without-parentheses"),
            pytest.param("AppRequests | extend x = toscalar(SecurityEvent | count) | summarize count()", id="v4-toscalar"),
            pytest.param('AppRequests | where Name == "//" | union workspace("other-ws").SecurityEvent | summarize count()', id="v4-comment-marker-in-string-hides-workspace"),
            pytest.param('AppRequests | where Name == "//" | evaluate http_request("https://evil.example/x")', id="v4-comment-marker-in-string-hides-evaluate"),
            pytest.param("union AppRequests, SecurityEvent | summarize count()", id="union-first-statement"),
            pytest.param("union kind=outer isfuzzy=true AppRequests, (SecurityEvent | take 1)", id="union-with-parameters-and-subquery"),
            pytest.param("union withsource=T SecurityEvent, AppRequests | take 5", id="union-with-source-name"),
            pytest.param("AppRequests | union (SecurityEvent | take 1)", id="union-parenthesised-subquery"),
            pytest.param("AppRequests | union Sec*", id="union-wildcard"),
            pytest.param("union *", id="union-star"),
            pytest.param("AppRequests | union App*", id="union-wildcard-of-allowed-prefix"),
            pytest.param("AppRequests | lookup kind=leftouter (SecurityEvent) on UserId", id="lookup-parenthesised"),
            pytest.param("AppRequests | join kind=inner hint.remote=auto SecurityEvent on Computer", id="join-with-dotted-hint"),
            pytest.param("AppRequests | extend x = materialize(SecurityEvent) | count", id="materialize"),
            pytest.param("AppRequests | where UserId in (SecurityEvent | project Account)", id="in-subquery"),
            pytest.param("AppRequests | where UserId in (SecurityEvent)", id="in-bare-table"),
            pytest.param("AppRequests | where Name has_any (SecurityEvent)", id="has-any-bare-table"),
            pytest.param("let t = SecurityEvent; AppRequests | take 1", id="let-statement-with-foreign-table"),
            pytest.param("let t = toscalar(SecurityEvent | count);", id="let-with-toscalar"),
            pytest.param("(SecurityEvent | take 1)", id="parenthesised-source"),
            pytest.param("((SecurityEvent) | take 1)", id="nested-parenthesised-source"),
            pytest.param("AppRequests | extend y = toscalar((SecurityEvent | take 1))", id="toscalar-nested-parentheses"),
            pytest.param("AppRequests | fork (take 1) (where 1==1) | union SecurityEvent", id="union-after-fork"),
            pytest.param("['SecurityEvent'] | take 1", id="bracket-quoted-table-name"),
            pytest.param('["SecurityEvent"] | take 1', id="double-bracket-quoted-table-name"),
            pytest.param("AppRequests | union ['SecurityEvent']", id="bracket-quoted-union-table"),
            pytest.param("AppRequests | join ['SecurityEvent'] on Computer", id="bracket-quoted-join-table"),
            pytest.param("securityevent | take 1", id="lower-case-foreign-table"),
            pytest.param('AppRequests | where Name == @"//" | union SecurityEvent', id="verbatim-string-with-comment-marker"),
            pytest.param("AppRequests | where Name == @'//' | union SecurityEvent", id="verbatim-single-quote-string-with-comment-marker"),
            pytest.param('AppRequests | where Name == h"//" | union SecurityEvent', id="obfuscated-string-with-comment-marker"),
            pytest.param("AppRequests | where Name == h'//' | union SecurityEvent", id="obfuscated-single-quote-string-with-comment-marker"),
            pytest.param('AppRequests | where Name == H@"//" | union SecurityEvent', id="obfuscated-verbatim-string-with-comment-marker"),
            pytest.param("AppRequests | where Name == ```//\n``` | union SecurityEvent", id="multi-line-string-with-comment-marker"),
            pytest.param("AppRequests | where Name == ~~~//\n~~~ | union SecurityEvent", id="tilde-multi-line-string-with-comment-marker"),
            pytest.param('AppRequests | where Name == "a\\"//" | union SecurityEvent', id="escaped-quote-then-comment-marker"),
            pytest.param('AppRequests | where Name == @"a""//" | union SecurityEvent', id="doubled-quote-in-verbatim-string"),
            pytest.param("AppRequests // comment\n| union SecurityEvent", id="comment-then-union"),
            pytest.param("AppRequests | where Name == 'x' // ; harmless\n| union SecurityEvent", id="comment-hides-nothing"),
            pytest.param('AppRequests | union workspace("w").AppRequests', id="union-workspace"),
            pytest.param('AppRequests | union app("a").requests', id="union-app"),
            pytest.param('AppRequests | union cluster("c").database("d").T', id="union-cluster-database"),
            pytest.param('AppRequests | union adx("https://c.kusto.windows.net/d").T', id="union-adx"),
            pytest.param('AppRequests | union arg("").Resources', id="union-azure-resource-graph"),
            pytest.param('database("d").AppRequests', id="database-function"),
            pytest.param("AppRequests | evaluate python(typeof(*), 'print(1)')", id="evaluate-python"),
            pytest.param("AppRequests | evaluate sql_request('Server=x', 'select 1')", id="evaluate-sql-request"),
            pytest.param("AppRequests | EVALUATE http_request('https://x')", id="evaluate-upper-case"),
            pytest.param("AppRequests | invoke fn()", id="invoke"),
            pytest.param("AppRequests | search 'x'", id="search-operator"),
            pytest.param("AppRequests | union (search 'x')", id="search-in-subquery"),
            pytest.param("search 'x'", id="search-first"),
            pytest.param("AppRequests | where Name == 'a'\n| find 'x'", id="find-later"),
            pytest.param("AppRequests | extend x = toscalar(externaldata (a:string) ['https://x'] | take 1)", id="externaldata-inside-toscalar"),
            pytest.param("set notruncation; AppRequests", id="query-option"),
            pytest.param("AppRequests; AppRequests", id="two-statements-same-table"),
            pytest.param("AppRequests | take 1;;SecurityEvent", id="double-semicolon"),
            pytest.param("AppRequests | take 1; SecurityEvent | union SecurityEvent", id="greek-question-mark-lookalike"),
            pytest.param("AppRequests | where Name == 'x' | union SecurityEvent​", id="zero-width-space-after-forbidden-table"),
            pytest.param("AppRequests | where (Name == 'x' | take 1", id="unbalanced-parenthesis"),
            pytest.param("AppRequests | where Name == 'unterminated | union SecurityEvent", id="unterminated-string"),
            pytest.param("AppRequests | where Name == ```never closed | union SecurityEvent", id="unterminated-multi-line-string"),
            pytest.param("print 1", id="print-is-not-a-table"),
            pytest.param("datatable(x:int)[1]", id="datatable-is-not-a-table"),
            pytest.param("range x from 1 to 10 step 1", id="range-is-not-a-table"),
            pytest.param("| take 1", id="leading-pipe"),
        ],
    )
    def test_rejects_every_known_bypass(self, query_text: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_kql(query_text, WINDOW_START, WINDOW_END)

    def test_names_the_allowed_tables_in_the_rejection_message(self) -> None:
        with pytest.raises(QueryRejectedError) as rejection:
            validate_kql("SecurityEvent | take 1", WINDOW_START, WINDOW_END)
        assert "AppRequests" in rejection.value.detail

    def test_uses_the_table_list_passed_by_the_caller(self) -> None:
        validate_kql("Heartbeat | summarize count()", WINDOW_START, WINDOW_END, allowed_tables=frozenset({"Heartbeat"}))
        with pytest.raises(QueryRejectedError):
            validate_kql("AppRequests | summarize count()", WINDOW_START, WINDOW_END, allowed_tables=frozenset({"Heartbeat"}))

    def test_a_trailing_semicolon_is_tolerated(self) -> None:
        validate_kql("AppRequests | summarize count();", WINDOW_START, WINDOW_END)

    def test_a_column_named_like_a_cross_resource_function_is_not_a_call(self) -> None:
        validate_kql("AppRequests | where AppRoleName == 'x' | project app = AppRoleName | summarize count()", WINDOW_START, WINDOW_END)

    def test_a_forbidden_word_inside_a_string_is_only_text(self) -> None:
        validate_kql("AppRequests | where Name has 'union workspace(x) evaluate find search externaldata' | summarize count()", WINDOW_START, WINDOW_END)


class TestValidateElasticQuery:
    def test_wraps_the_query_in_the_time_window_and_caps_size(self) -> None:
        hardened = json.loads(validate_elastic_query(json.dumps({"query": {"match": {"level": "error"}}, "size": 10_000}), WINDOW_START, WINDOW_END).query_text)
        assert hardened == {
            "query": {
                "bool": {
                    "filter": [{"range": {"@timestamp": {"gte": "2026-11-20T11:00:00+00:00", "lte": "2026-11-20T12:00:00+00:00"}}}],
                    "must": [{"match": {"level": "error"}}],
                }
            },
            "size": 500,
        }

    def test_defaults_the_size_when_missing(self) -> None:
        assert json.loads(validate_elastic_query(json.dumps({"query": {"match_all": {}}}), WINDOW_START, WINDOW_END).query_text)["size"] == 100

    def test_keeps_a_size_of_zero_for_aggregation_only_queries(self) -> None:
        assert json.loads(validate_elastic_query(json.dumps({"size": 0}), WINDOW_START, WINDOW_END).query_text)["size"] == 0

    def test_clamps_a_negative_size_to_zero(self) -> None:
        assert json.loads(validate_elastic_query(json.dumps({"size": -5}), WINDOW_START, WINDOW_END).query_text)["size"] == 0

    def test_bounds_the_size_of_every_aggregation(self) -> None:
        body = {"size": 0, "aggs": {"top": {"terms": {"field": "message.keyword", "size": 1_000_000}, "aggs": {"inner": {"terms": {"field": "host", "size": 50}}}}}}
        hardened = json.loads(validate_elastic_query(json.dumps(body), WINDOW_START, WINDOW_END).query_text)
        assert hardened["aggs"]["top"]["terms"]["size"] == 100
        assert hardened["aggs"]["top"]["aggs"]["inner"]["terms"]["size"] == 50

    @pytest.mark.parametrize(
        "query_text",
        [
            pytest.param(json.dumps({"query": {"script": {"script": "doc['a'].value > 1"}}}), id="script-query"),
            pytest.param(json.dumps({"query": {"match_all": {}}, "script_fields": {}}), id="unexpected-top-level-key"),
            pytest.param("not json", id="not-json"),
            pytest.param(json.dumps(["a list"]), id="not-an-object"),
            pytest.param('{"query":{"bool":{"filter":[{"scr\\u0069pt":{"scr\\u0069pt":{"source":"doc[\'x\'].value > 0"}}}]}}}', id="v6-unicode-escaped-script-key"),
            pytest.param(json.dumps({"query": {"bool": {"filter": [{"script": {"script": {"source": "1 == 1"}}}]}}}), id="script-nested-in-a-bool-filter"),
            pytest.param(json.dumps({"aggs": {"x": {"scripted_metric": {"init_script": "state.a = 1", "map_script": "1", "combine_script": "1", "reduce_script": "1"}}}}), id="scripted-metric"),
            pytest.param(json.dumps({"aggs": {"x": {"terms": {"script": {"source": "doc['a'].value"}}}}}), id="script-inside-an-aggregation"),
            pytest.param(json.dumps({"query": {"match_all": {}}, "aggs": {"x": {"terms": {"field": "a"}}}, "runtime_mappings": {"x": {"type": "keyword", "script": "emit(1)"}}}), id="runtime-mappings-at-top-level"),
            pytest.param(json.dumps({"query": {"function_score": {"query": {"match_all": {}}, "script_score": {"script": {"source": "1"}}}}}), id="script-score"),
            pytest.param(json.dumps({"sort": [{"_script": {"type": "number", "script": {"source": "1"}, "order": "asc"}}]}), id="script-sort"),
            pytest.param(json.dumps({"query": {"terms": {"user": {"index": "secrets", "id": "1", "path": "names"}}}}), id="terms-lookup-in-another-index"),
            pytest.param(json.dumps({"query": {"geo_shape": {"location": {"indexed_shape": {"index": "secrets", "id": "1", "path": "shape"}}}}}), id="indexed-shape-lookup"),
            pytest.param(json.dumps({"size": "abc"}), id="size-is-text"),
            pytest.param(json.dumps({"size": 1.5}), id="size-is-a-float"),
            pytest.param(json.dumps({"size": True}), id="size-is-a-boolean"),
            pytest.param(json.dumps({"size": None}), id="size-is-null"),
            pytest.param(json.dumps({"size": [1]}), id="size-is-a-list"),
            pytest.param(json.dumps({"aggs": {"x": {"terms": {"field": "a", "size": "many"}}}}), id="aggregation-size-is-text"),
            pytest.param(json.dumps({"query": "match_all"}), id="query-is-not-an-object"),
            pytest.param("[" * 5000 + "]" * 5000, id="deeply-nested-json"),
            pytest.param(json.dumps({"query": {"match": {"a": "b"}}, "size": 5, "from": 100000}), id="from-is-not-supported"),
        ],
    )
    def test_rejects_unsafe_queries(self, query_text: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_elastic_query(query_text, WINDOW_START, WINDOW_END)

    def test_the_word_script_in_a_search_value_is_only_text(self) -> None:
        hardened = json.loads(validate_elastic_query(json.dumps({"query": {"match": {"message": "transcript of the script was saved"}}}), WINDOW_START, WINDOW_END).query_text)
        assert hardened["query"]["bool"]["must"] == [{"match": {"message": "transcript of the script was saved"}}]

    def test_rejection_message_for_a_script_names_the_key(self) -> None:
        with pytest.raises(QueryRejectedError) as rejection:
            validate_elastic_query(json.dumps({"query": {"script": {"script": "1"}}}), WINDOW_START, WINDOW_END)
        assert "script" in rejection.value.detail


class TestValidateElasticIndexPattern:
    @pytest.mark.parametrize("index_pattern", ["logs-*", "logs-chad-*", "app_logs.2026", "logs-a*,logs-b*", "filebeat-8.12.0-*"])
    def test_accepts_ordinary_index_patterns(self, index_pattern: str) -> None:
        assert validate_elastic_index_pattern(index_pattern) == index_pattern

    @pytest.mark.parametrize(
        "index_pattern",
        [
            pytest.param("logs-*/_delete_by_query#", id="s2-path-and-fragment"),
            pytest.param("logs-*/_delete_by_query", id="path-segment"),
            pytest.param("logs-*#", id="fragment"),
            pytest.param("logs-*?refresh=true", id="query-string"),
            pytest.param("..", id="parent-directory"),
            pytest.param("logs-..-secret", id="embedded-parent-directory"),
            pytest.param("logs *", id="whitespace"),
            pytest.param("logs-*\n", id="newline"),
            pytest.param("logs-%2F_delete", id="percent-encoding"),
            pytest.param("remote:logs-*", id="cross-cluster-search"),
            pytest.param("_cat", id="leading-underscore-api-name"),
            pytest.param("logs-*,_all", id="underscore-component-in-list"),
            pytest.param("logs\\evil", id="backslash"),
            pytest.param("logs-é", id="non-ascii"),
            pytest.param("", id="empty"),
            pytest.param("a" * 300, id="too-long"),
        ],
    )
    def test_rejects_patterns_that_can_change_the_request_path(self, index_pattern: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_elastic_index_pattern(index_pattern)


class TestValidateSpl:
    def test_forces_the_configured_index_and_the_investigation_window(self) -> None:
        hardened = validate_spl("error", WINDOW_START, WINDOW_END, required_index="app")
        assert hardened.query_text == f"search index=app earliest={EPOCH_START} latest={EPOCH_END} error | head 500"

    def test_replaces_user_time_bounds_with_the_investigation_window(self) -> None:
        hardened = validate_spl("index=app error earliest=-30d latest=now", WINDOW_START, WINDOW_END, required_index="app")
        assert hardened.query_text.startswith(f"search index=app earliest={EPOCH_START} latest={EPOCH_END} ")
        assert "-30d" not in hardened.query_text
        assert "now" not in hardened.query_text

    def test_caps_rows_when_the_search_has_no_limit(self) -> None:
        assert validate_spl("index=app error", WINDOW_START, WINDOW_END, required_index="app").query_text.endswith("| head 500")

    def test_leaves_aggregations_without_a_row_cap(self) -> None:
        assert "head" not in validate_spl("error | stats count by host", WINDOW_START, WINDOW_END, required_index="app").query_text

    def test_accepts_the_commands_on_the_allow_list(self) -> None:
        query = 'error | eval ok=if(status<500,1,0) | rex field=_raw "(?<code>\\d+)" | where code>0 | fields host, code | stats count by host | sort - count | head 10'
        validate_spl(query, WINDOW_START, WINDOW_END, required_index="app")

    def test_a_pipe_inside_a_quoted_string_is_not_a_command(self) -> None:
        validate_spl('error | rex field=_raw "(?<x>aa|bb)" | stats count', WINDOW_START, WINDOW_END, required_index="app")

    @pytest.mark.parametrize(
        "command",
        ["sendemail", "outputlookup", "delete", "script", "rest", "collect", "summaryindex", "runshellscript", "inputlookup", "map", "tscollect", "mcollect", "run", "dbxquery", "sendalert", "outputcsv", "loadjob", "savedsearch", "append", "join", "union", "multisearch", "lookup", "datamodel", "from", "pivot", "metadata", "eventcount", "makeresults", "gentimes", "mstats", "mpreview", "outputtext"],
    )
    def test_rejects_every_command_that_is_not_on_the_allow_list(self, command: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_spl(f"index=app | {command} something", WINDOW_START, WINDOW_END, required_index="app")

    @pytest.mark.parametrize(
        "query_text",
        [
            pytest.param("search index=secret password | stats count by user", id="v5-other-index"),
            pytest.param("index=main OR index=secret error", id="second-index-in-or"),
            pytest.param("(index=main OR index=secret) error", id="second-index-in-parentheses"),
            pytest.param("index!=main error", id="index-negation"),
            pytest.param("index IN (main, secret) error", id="index-in-list"),
            pytest.param("index::secret error", id="index-double-colon"),
            pytest.param('index="secret" error', id="index-quoted"),
            pytest.param("INDEX=secret error", id="index-upper-case"),
            pytest.param("search index=main | `exfil_macro`", id="v5-macro"),
            pytest.param("error `exfil_macro`", id="macro-in-search-terms"),
            pytest.param('error "`exfil_macro`"', id="macro-inside-quotes"),
            pytest.param("search index=main | summaryindex index=stolen", id="v5-summaryindex"),
            pytest.param("search index=main | runshellscript x.sh", id="v5-runshellscript"),
            pytest.param("search index=main | inputlookup users.csv", id="v5-inputlookup"),
            pytest.param("error [search index=secret | fields host]", id="subsearch"),
            pytest.param("error | search [search index=secret | fields host]", id="subsearch-in-later-search"),
            pytest.param("error [", id="open-bracket"),
            pytest.param("error | stats count | outputlookup x", id="write-after-stats"),
            pytest.param("error | eval x=1 | MAP search=\"x\"", id="upper-case-command"),
            pytest.param("| inputlookup users.csv", id="leading-pipe-not-tstats"),
            pytest.param("| makeresults", id="generating-command"),
            pytest.param('error "unterminated | delete', id="unterminated-quote-hides-delete"),
            pytest.param('error \\" | delete x \\"', id="escaped-quote-outside-string"),
            pytest.param("error |", id="empty-command"),
            pytest.param("error || delete x", id="double-pipe"),
            pytest.param("", id="empty"),
            pytest.param("   ", id="blank"),
            pytest.param("error; | delete x", id="non-ascii-lookalike"),
        ],
    )
    def test_rejects_unsafe_queries(self, query_text: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_spl(query_text, WINDOW_START, WINDOW_END, required_index="main")

    def test_replaces_a_wildcard_index_with_the_configured_index(self) -> None:
        hardened = validate_spl("search index=* password | stats count by user", WINDOW_START, WINDOW_END, required_index="main")
        assert hardened.query_text == f"search index=main earliest={EPOCH_START} latest={EPOCH_END} password | stats count by user"

    def test_rejects_a_search_when_no_index_is_configured(self) -> None:
        with pytest.raises(QueryRejectedError) as rejection:
            validate_spl("error", WINDOW_START, WINDOW_END, required_index=None)
        assert "index" in rejection.value.detail

    def test_accepts_the_configured_index_written_by_the_model_and_does_not_repeat_it(self) -> None:
        hardened = validate_spl('index="main" error', WINDOW_START, WINDOW_END, required_index="main")
        assert hardened.query_text.count("index=") == 1

    def test_bounds_tstats_with_the_index_and_the_window(self) -> None:
        hardened = validate_spl("| tstats count where index=* earliest=0 by _time span=1d", WINDOW_START, WINDOW_END, required_index="main")
        assert hardened.query_text == f"| tstats count where index=main earliest={EPOCH_START} latest={EPOCH_END} by _time span=1d"

    def test_adds_a_where_clause_to_tstats_that_has_none(self) -> None:
        hardened = validate_spl("| tstats count by host", WINDOW_START, WINDOW_END, required_index="main")
        assert hardened.query_text == f"| tstats count where index=main earliest={EPOCH_START} latest={EPOCH_END} by host"

    def test_adds_a_where_clause_to_tstats_that_has_no_by_clause(self) -> None:
        hardened = validate_spl("| tstats count", WINDOW_START, WINDOW_END, required_index="main")
        assert hardened.query_text == f"| tstats count where index=main earliest={EPOCH_START} latest={EPOCH_END}"

    def test_rejects_tstats_over_a_different_index_in_the_where_clause(self) -> None:
        with pytest.raises(QueryRejectedError):
            validate_spl("| tstats count where index=secret by host", WINDOW_START, WINDOW_END, required_index="main")

    def test_reads_the_splunk_index_from_the_log_source_scope(self) -> None:
        assert configured_splunk_index({"index": "zos_syslog"}) == "zos_syslog"
        assert configured_splunk_index({"index_pattern": "zos_syslog"}) == "zos_syslog"

    @pytest.mark.parametrize("scope", [None, {}, {"index": ""}, {"index": "*"}, {"index": "a b"}, {"index": "main OR index=secret"}, {"index": "logs-*"}, {"index": 5}])
    def test_ignores_a_scope_without_a_plain_index_name(self, scope: dict[str, Any] | None) -> None:
        assert configured_splunk_index(scope) is None


class TestValidateGeneratedQuery:
    def test_routes_spl_with_the_index_of_the_log_source_scope(self) -> None:
        hardened = validate_generated_query("spl", "error", WINDOW_START, WINDOW_END, query_scope={"index": "zos_syslog"})
        assert hardened.query_text.startswith("search index=zos_syslog earliest=")

    def test_rejects_spl_when_the_log_source_has_no_index(self) -> None:
        with pytest.raises(QueryRejectedError):
            validate_generated_query("spl", "error", WINDOW_START, WINDOW_END, query_scope={})

    def test_routes_kql_and_elastic(self) -> None:
        assert validate_generated_query("kql", "AppRequests | summarize count()", WINDOW_START, WINDOW_END).query_language == "kql"
        assert validate_generated_query("elastic_dsl", '{"size": 0}', WINDOW_START, WINDOW_END).query_language == "elastic_dsl"

    def test_rejects_a_language_it_cannot_run(self) -> None:
        with pytest.raises(QueryRejectedError):
            validate_generated_query("sql", "select 1", WINDOW_START, WINDOW_END)


class TestKeigansOwnEvidenceTemplatesStillPass:
    """The shipped templates are the realistic shape of a good query; a stricter validator must not break them."""

    @staticmethod
    def _templates(query_language: str) -> list[dict[str, Any]]:
        from keigan.services.evidence_service import load_query_templates

        return [template for template in load_query_templates() if template["query_language"] == query_language]

    def test_kql_templates(self) -> None:
        templates = self._templates("kql")
        assert len(templates) >= 10
        for template in templates:
            query = template["query_text"].replace("${role_name}", "claims-api").replace("${namespace}", "claims").replace("${service_name}", "claims-api")
            validate_kql(query, WINDOW_START, WINDOW_END)

    def test_elastic_templates(self) -> None:
        for template in self._templates("elastic_dsl"):
            validate_elastic_query(template["query_text"].replace("${service_name}", "claims-api"), WINDOW_START, WINDOW_END)

    def test_splunk_templates(self) -> None:
        templates = self._templates("spl")
        assert templates
        for template in templates:
            validate_spl(template["query_text"].replace("${index_pattern}", "zos_syslog").replace("${service_name}", "batch"), WINDOW_START, WINDOW_END, required_index="zos_syslog")


class TestDescribeQueryLimits:
    def test_kql_lists_the_allowed_tables(self) -> None:
        limits = describe_query_limits("kql")
        assert limits["queryLanguage"] == "kql"
        assert "AppRequests" in limits["allowedTables"]
        assert "SecurityEvent" not in limits["allowedTables"]

    def test_spl_names_the_index_of_the_log_source_and_the_allowed_commands(self) -> None:
        limits = describe_query_limits("spl", {"index": "zos_syslog"})
        assert limits["index"] == "zos_syslog"
        assert "stats" in limits["allowedCommands"]
        assert "outputlookup" not in limits["allowedCommands"]

    def test_elastic_gives_the_index_and_field_names_that_the_log_source_configures(self) -> None:
        limits = describe_query_limits("elastic_dsl", {"index_pattern": "logs-chad-*"}, {"service_field": "service.name", "time_field": "@timestamp"})
        assert limits["indexPattern"] == "logs-chad-*"
        assert limits["serviceField"] == "service.name"
        assert limits["timeField"] == "@timestamp"
        assert "query" in limits["allowedTopLevelKeys"]

    def test_elastic_does_not_invent_fields_the_log_source_does_not_configure(self) -> None:
        assert "serviceField" not in describe_query_limits("elastic_dsl", {"index_pattern": "logs-*"}, {})


class TestPromptsMatchTheValidator:
    def test_every_table_named_in_the_chat_prompt_is_allowed(self) -> None:
        prompt = PromptLibrary().render("ai_chat_query_generation")
        named_tables = set(re.findall(r"`([A-Z][A-Za-z0-9]+)` \(", prompt))
        assert {"AppRequests", "ContainerLogV2"} <= named_tables
        assert named_tables <= load_query_safety_policy().allowed_kql_tables

    @pytest.mark.parametrize("prompt_key", ["ai_chat_query_generation", "evidence_query_planner"])
    def test_the_prompts_do_not_teach_a_search_over_every_index(self, prompt_key: str) -> None:
        assert "index=*" not in PromptLibrary().render(prompt_key, application_name="Claims")
