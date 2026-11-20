"""keigan/utils/query_safety.py: validation and hardening of generated KQL, Elastic DSL and Splunk SPL."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from keigan.utils.query_safety import QueryRejectedError, validate_elastic_query, validate_kql, validate_spl

WINDOW_END = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
WINDOW_START = WINDOW_END - timedelta(hours=1)


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

    @pytest.mark.xfail(strict=True, reason="H2: tables referenced by a later `| union` are not checked")
    def test_rejects_union_with_a_table_that_is_not_allowed(self) -> None:
        with pytest.raises(QueryRejectedError):
            validate_kql("AppRequests | union SecurityEvent | take 10", WINDOW_START, WINDOW_END)


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

    @pytest.mark.parametrize(
        "query_text",
        [
            pytest.param(json.dumps({"query": {"script": {"script": "doc['a'].value > 1"}}}), id="script-query"),
            pytest.param(json.dumps({"query": {"match_all": {}}, "script_fields": {}}), id="unexpected-top-level-key"),
            pytest.param("not json", id="not-json"),
            pytest.param(json.dumps(["a list"]), id="not-an-object"),
        ],
    )
    def test_rejects_unsafe_queries(self, query_text: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_elastic_query(query_text, WINDOW_START, WINDOW_END)


class TestValidateSpl:
    def test_replaces_user_time_bounds_with_the_investigation_window(self) -> None:
        hardened = validate_spl("index=app error earliest=-30d", WINDOW_START, WINDOW_END)
        # 2026-11-20 11:00 and 12:00 UTC as Unix seconds (2026-01-01 = 1767225600, + 323 days + 11 h / 12 h).
        assert hardened.query_text.startswith("search earliest=1795172400 latest=1795176000 index=app error")
        assert "-30d" not in hardened.query_text

    def test_caps_rows_when_the_search_has_no_limit(self) -> None:
        assert validate_spl("index=app error", WINDOW_START, WINDOW_END).query_text.endswith("| head 500")

    @pytest.mark.parametrize("command", ["sendemail", "outputlookup", "delete", "script", "rest"])
    def test_rejects_commands_that_write_or_call_out(self, command: str) -> None:
        with pytest.raises(QueryRejectedError):
            validate_spl(f"index=app | {command} something", WINDOW_START, WINDOW_END)
