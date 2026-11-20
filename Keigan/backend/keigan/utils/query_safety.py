"""Validation and hardening of AI-generated telemetry queries (KQL, Elastic Query DSL, Splunk SPL).

Generated queries are untrusted. They must be read-only, single-statement, bounded in time and rows, and may
only touch allow-listed tables / indices for the data source. :func:`validate_generated_query` returns the
hardened query text or raises :class:`QueryRejectedError` with a human-readable reason.

What the policy allows lives in ``resources/catalogs/query_safety.yaml``. KQL is checked on a token stream (strings and
comments are removed by a real tokenizer, so no string literal can hide code); SPL is checked against a command
allow-list; Elastic is checked on the parsed JSON tree, never on its text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

import yaml

from keigan.config.settings import RESOURCES_DIRECTORY
from keigan.exceptions.keigan_exceptions import BusinessValidationException

QUERY_SAFETY_POLICY_PATH = RESOURCES_DIRECTORY / "catalogs" / "query_safety.yaml"
SPLUNK_INDEX_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,79}$")
ELASTIC_INDEX_PATTERN_CHARACTERS = re.compile(r"^[A-Za-z0-9_.*,\-]+$")


class QueryRejectedError(BusinessValidationException):
    error_code = "query_rejected"
    title = "Keigan rejected a generated query"


@dataclass(frozen=True)
class QuerySafetyPolicy:
    maximum_query_characters: int
    maximum_result_rows: int
    elastic_default_size: int
    elastic_maximum_aggregation_size: int
    elastic_maximum_json_depth: int
    elastic_maximum_index_pattern_characters: int
    allowed_kql_tables: frozenset[str]
    sli_allowed_kql_tables: frozenset[str]
    forbidden_kql_keywords: Mapping[str, str]
    forbidden_kql_functions: frozenset[str]
    forbidden_kql_leading_keywords: frozenset[str]
    kql_tabular_operators: frozenset[str]
    allowed_spl_commands: frozenset[str]
    allowed_spl_generating_commands: frozenset[str]
    spl_row_limiting_commands: frozenset[str]
    allowed_elastic_top_level_keys: frozenset[str]
    forbidden_elastic_keys: frozenset[str]


@lru_cache
def load_query_safety_policy() -> QuerySafetyPolicy:
    catalog = yaml.safe_load(QUERY_SAFETY_POLICY_PATH.read_text(encoding="utf-8"))
    limits, kql, spl, elastic = catalog["limits"], catalog["kql"], catalog["spl"], catalog["elastic"]
    return QuerySafetyPolicy(
        maximum_query_characters=int(limits["maximum_query_characters"]),
        maximum_result_rows=int(limits["maximum_result_rows"]),
        elastic_default_size=int(limits["elastic_default_size"]),
        elastic_maximum_aggregation_size=int(limits["elastic_maximum_aggregation_size"]),
        elastic_maximum_json_depth=int(limits["elastic_maximum_json_depth"]),
        elastic_maximum_index_pattern_characters=int(limits["elastic_maximum_index_pattern_characters"]),
        allowed_kql_tables=frozenset(kql["allowed_tables"]),
        sli_allowed_kql_tables=frozenset(kql["sli_allowed_tables"]),
        forbidden_kql_keywords={keyword.lower(): reason for keyword, reason in kql["forbidden_keywords"].items()},
        forbidden_kql_functions=frozenset(function_name.lower() for function_name in kql["forbidden_functions"]),
        forbidden_kql_leading_keywords=frozenset(kql["forbidden_leading_keywords"]),
        kql_tabular_operators=frozenset(kql["tabular_operators"]),
        allowed_spl_commands=frozenset(spl["allowed_commands"]),
        allowed_spl_generating_commands=frozenset(spl["allowed_generating_commands"]),
        spl_row_limiting_commands=frozenset(spl["row_limiting_commands"]),
        allowed_elastic_top_level_keys=frozenset(elastic["allowed_top_level_keys"]),
        forbidden_elastic_keys=frozenset(elastic["forbidden_keys"]),
    )


# Kept as module names because callers import them: the catalog is the single source of the values.
MAXIMUM_RESULT_ROWS = load_query_safety_policy().maximum_result_rows
DEFAULT_ALLOWED_KQL_TABLES = load_query_safety_policy().allowed_kql_tables


def sli_allowed_kql_tables() -> frozenset[str]:
    """Tables a custom SLI query may read (narrower than the chat and planner list)."""
    return load_query_safety_policy().sli_allowed_kql_tables


@dataclass(frozen=True)
class HardenedQuery:
    query_language: str
    query_text: str
    applied_hardening: tuple[str, ...]


def _format_kql_datetime(timestamp: datetime) -> str:
    return f"datetime({timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')})"


# ── KQL: tokenizer ─────────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Token:
    kind: str  # identifier | quoted_identifier | string | number | punctuation
    text: str
    start: int


_KQL_TWO_CHARACTER_OPERATORS = ("==", "=~", "!=", "!~", "<=", ">=", "<>", "..")
_KQL_MULTI_LINE_DELIMITERS = ("```", "~~~")
_KQL_ALLOWED_WHITESPACE = " \t\r\n"


def _reject(reason: str) -> QueryRejectedError:
    return QueryRejectedError(f"The query was rejected: {reason}.")


def _read_string_end(text: str, quote_index: int, *, is_verbatim: bool) -> int:
    """Index just after the closing quote of the string whose opening quote is at ``quote_index``."""
    quote = text[quote_index]
    position = quote_index + 1
    while position < len(text):
        current = text[position]
        if is_verbatim:
            if current == quote:
                if text[position + 1 : position + 2] == quote:  # a doubled quote is the only escape in verbatim strings
                    position += 2
                    continue
                return position + 1
        elif current == "\\":
            position += 2
            continue
        elif current == quote:
            return position + 1
        position += 1
    raise _reject("a text value is not closed")


def _read_kql_string(text: str, start: int) -> tuple[int, str] | None:
    """If a string literal (any KQL form) starts at ``start``, return (index after it, its content)."""
    for delimiter in _KQL_MULTI_LINE_DELIMITERS:
        if text.startswith(delimiter, start):
            closing_index = text.find(delimiter, start + len(delimiter))
            if closing_index == -1:
                raise _reject("a multi-line text value is not closed")
            return closing_index + len(delimiter), text[start + len(delimiter) : closing_index]
    prefix_length = 0
    if text[start] in "hH" and start + 1 < len(text) and text[start + 1] in "\"'@":
        prefix_length = 1  # obfuscated string: h"..." h'...' h@"..."
    position = start + prefix_length
    is_verbatim = position < len(text) and text[position] == "@" and position + 1 < len(text) and text[position + 1] in "\"'"
    if is_verbatim:
        position += 1
    if position < len(text) and text[position] in "\"'" and (prefix_length or is_verbatim or position == start):
        end = _read_string_end(text, position, is_verbatim=is_verbatim)
        return end, text[position + 1 : end - 1]
    return None


def _tokenize_kql(text: str) -> list[_Token]:
    """Split KQL into tokens. String literals (every form) and comments never reach the rules that look for code."""
    tokens: list[_Token] = []
    position = 0
    while position < len(text):
        character = text[position]
        if character in _KQL_ALLOWED_WHITESPACE:
            position += 1
        elif text.startswith("//", position):
            line_end = text.find("\n", position)
            position = len(text) if line_end == -1 else line_end
        elif (string_literal := _read_kql_string(text, position)) is not None:
            tokens.append(_Token("string", string_literal[1], position))
            position = string_literal[0]
        elif character == "[" and (quoted_name := _read_bracketed_name(text, position)) is not None:
            tokens.append(_Token("quoted_identifier", quoted_name[1], position))
            position = quoted_name[0]
        elif character.isascii() and (character.isalpha() or character in "_$"):
            end = position
            while end < len(text) and text[end].isascii() and (text[end].isalnum() or text[end] in "_$"):
                end += 1
            tokens.append(_Token("identifier", text[position:end], position))
            position = end
        elif character.isascii() and character.isdigit():
            end = position
            while end < len(text) and text[end].isascii() and (text[end].isalnum() or text[end] in "_."):
                end += 1
            tokens.append(_Token("number", text[position:end], position))
            position = end
        elif character.isascii() and character.isprintable():
            operator = next((candidate for candidate in _KQL_TWO_CHARACTER_OPERATORS if text.startswith(candidate, position)), character)
            tokens.append(_Token("punctuation", operator, position))
            position += len(operator)
        else:
            raise _reject(f"it contains the character {character!r}, which KQL does not use outside text values")
    return tokens


def _read_bracketed_name(text: str, start: int) -> tuple[int, str] | None:
    """``['name']`` / ``["name"]``: a quoted identifier, which can name a table. Returns (index after ']', name)."""
    position = start + 1
    while position < len(text) and text[position] in _KQL_ALLOWED_WHITESPACE:
        position += 1
    if position >= len(text) or text[position] not in "\"'":
        return None
    end = _read_string_end(text, position, is_verbatim=False)
    name = text[position + 1 : end - 1]
    while end < len(text) and text[end] in _KQL_ALLOWED_WHITESPACE:
        end += 1
    if end >= len(text) or text[end] != "]":
        return None
    return end + 1, name


# ── KQL: structure ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _matching_parentheses(tokens: list[_Token]) -> dict[int, int]:
    """Map the index of every opening parenthesis to its closing one; unbalanced parentheses are rejected."""
    matches: dict[int, int] = {}
    open_positions: list[int] = []
    for index, token in enumerate(tokens):
        if token.kind != "punctuation":
            continue
        if token.text == "(":
            open_positions.append(index)
        elif token.text == ")":
            if not open_positions:
                raise _reject("the parentheses do not match")
            matches[open_positions.pop()] = index
    if open_positions:
        raise _reject("the parentheses do not match")
    return matches


def _is_punctuation(tokens: list[_Token], index: int, text: str) -> bool:
    return 0 <= index < len(tokens) and tokens[index].kind == "punctuation" and tokens[index].text == text


def _is_keyword(tokens: list[_Token], index: int, *keywords: str) -> bool:
    return 0 <= index < len(tokens) and tokens[index].kind == "identifier" and tokens[index].text.lower() in keywords and not _is_punctuation(tokens, index - 1, ".")


def _has_top_level_pipe(tokens: list[_Token], open_index: int, close_index: int) -> bool:
    depth = 0
    for token in tokens[open_index + 1 : close_index]:
        if token.kind != "punctuation":
            continue
        if token.text == "(":
            depth += 1
        elif token.text == ")":
            depth -= 1
        elif token.text == "|" and depth == 0:
            return True
    return False


def _skip_keyword_parameters(tokens: list[_Token], index: int) -> int:
    """Skip ``kind=inner``, ``isfuzzy=true``, ``hint.remote=auto`` style parameters; return the index after them."""
    while index < len(tokens) and tokens[index].kind == "identifier":
        name_end = index
        while _is_punctuation(tokens, name_end + 1, ".") and name_end + 2 < len(tokens) and tokens[name_end + 2].kind == "identifier":
            name_end += 2
        if not _is_punctuation(tokens, name_end + 1, "="):
            break
        index = name_end + 3
    return index


class _TableReferenceFinder:
    """Finds every position in a KQL token stream where a table (or a sub-query that reads tables) is referenced."""

    def __init__(self, tokens: list[_Token], policy: QuerySafetyPolicy):
        self.tokens = tokens
        self.policy = policy
        self.closing_by_opening = _matching_parentheses(tokens)
        self.table_positions: dict[int, bool] = {}  # token index -> is the first word of a sub-query (may be an operator)

    def find(self) -> dict[int, bool]:
        if not _is_keyword(self.tokens, 0, "union"):  # a leading union names its tables itself
            self._mark(0, is_subquery_start=False)
        for index, token in enumerate(self.tokens):
            if token.kind == "identifier" and not _is_punctuation(self.tokens, index - 1, "."):
                self._mark_after_keyword(index, token.text.lower())
            elif token.kind == "punctuation" and token.text == "(":
                self._mark_parenthesis(index)
        return self.table_positions

    def _mark(self, index: int, *, is_subquery_start: bool) -> None:
        if index >= len(self.tokens):
            return
        if _is_punctuation(self.tokens, index, "("):
            self._mark(index + 1, is_subquery_start=True)
            return
        self.table_positions[index] = is_subquery_start

    def _mark_after_keyword(self, index: int, keyword: str) -> None:
        next_index = index + 1
        if keyword in ("toscalar", "materialize") and _is_punctuation(self.tokens, next_index, "("):
            self._mark(next_index, is_subquery_start=True)
        elif keyword == "union":
            self._mark_union_sources(next_index)
        elif keyword in ("join", "lookup") and not _is_punctuation(self.tokens, next_index, "=") and not _is_punctuation(self.tokens, next_index, "."):
            self._mark_right_hand_side(self._skip_parameters(next_index))

    def _skip_parameters(self, index: int) -> int:
        return _skip_keyword_parameters(self.tokens, index)

    def _mark_right_hand_side(self, index: int) -> None:
        if index < len(self.tokens) and (self.tokens[index].kind in ("identifier", "quoted_identifier") or _is_punctuation(self.tokens, index, "(") or _is_punctuation(self.tokens, index, "*")):
            self._mark(index, is_subquery_start=False)

    def _mark_union_sources(self, index: int) -> None:
        index = self._skip_parameters(index)
        while index < len(self.tokens):
            token = self.tokens[index]
            if _is_punctuation(self.tokens, index, "("):
                self._mark(index, is_subquery_start=False)
                index = self.closing_by_opening[index] + 1
            elif token.kind in ("identifier", "quoted_identifier") or _is_punctuation(self.tokens, index, "*"):
                self._mark(index, is_subquery_start=False)
                index += 1
            else:
                return
            while _is_punctuation(self.tokens, index, "*"):  # a trailing wildcard such as Sec*
                index += 1
            if not _is_punctuation(self.tokens, index, ","):
                return
            index += 1

    def _mark_parenthesis(self, open_index: int) -> None:
        close_index = self.closing_by_opening[open_index]
        previous = self.tokens[open_index - 1] if open_index else None
        previous_keyword = previous.text.lower() if previous and previous.kind == "identifier" else ""
        is_after_membership_operator = previous_keyword in ("in", "has_any", "has_all", "contains_all") or (
            _is_punctuation(self.tokens, open_index - 1, "~") and open_index >= 2 and self.tokens[open_index - 2].text.lower() in ("in", "has_any", "has_all")
        )
        if _has_top_level_pipe(self.tokens, open_index, close_index):
            self._mark(open_index + 1, is_subquery_start=True)
        elif is_after_membership_operator and close_index == open_index + 2 and self.tokens[open_index + 1].kind in ("identifier", "quoted_identifier"):
            self._mark(open_index + 1, is_subquery_start=False)
        elif previous_keyword == "fork":
            self._mark(open_index + 1, is_subquery_start=True)


def _referenced_table_problems(tokens: list[_Token], policy: QuerySafetyPolicy, allowed_tables: frozenset[str]) -> list[str]:
    """Names (or descriptions) of table references that are not on the allow-list; empty when every reference is allowed."""
    problems: list[str] = []
    positions = _TableReferenceFinder(tokens, policy).find()
    if not positions:
        problems.append("(no table)")
    for index, is_subquery_start in positions.items():
        token = tokens[index]
        if _is_punctuation(tokens, index, "*") or _is_punctuation(tokens, index + 1, "*"):
            problems.append("a wildcard table name")
        elif token.kind == "quoted_identifier" or token.kind == "identifier":
            if is_subquery_start and token.kind == "identifier" and token.text.lower() in policy.kql_tabular_operators:
                continue  # fork (take 1): an operator applied to the implicit source, not a table
            if token.text not in allowed_tables:
                problems.append(token.text)
        else:
            problems.append(token.text)
    return problems


def _check_kql_forbidden_content(tokens: list[_Token], policy: QuerySafetyPolicy) -> None:
    if not tokens:
        raise QueryRejectedError("The query is empty or too long.")
    if _is_punctuation(tokens, 0, "."):
        raise _reject("management commands are not allowed")
    if tokens[0].kind == "identifier" and tokens[0].text.lower() in policy.forbidden_kql_leading_keywords:
        raise _reject("query options, declarations and let statements are not allowed")
    for index, token in enumerate(tokens):
        if token.kind == "punctuation" and token.text == ";":
            raise _reject("only one statement is allowed")
        if token.kind != "identifier" or _is_punctuation(tokens, index - 1, "."):
            continue
        keyword = token.text.lower()
        if keyword in policy.forbidden_kql_keywords:
            raise _reject(policy.forbidden_kql_keywords[keyword])
        if keyword in policy.forbidden_kql_functions and _is_punctuation(tokens, index + 1, "("):
            raise _reject("cross-resource queries are not allowed")


def _drop_trailing_semicolons(tokens: list[_Token]) -> list[_Token]:
    while tokens and tokens[-1].kind == "punctuation" and tokens[-1].text == ";":
        tokens = tokens[:-1]
    return tokens


def _top_level_pipe_indexes(tokens: list[_Token]) -> list[int]:
    depth = 0
    pipe_indexes: list[int] = []
    for index, token in enumerate(tokens):
        if token.kind != "punctuation":
            continue
        if token.text == "(":
            depth += 1
        elif token.text == ")":
            depth -= 1
        elif token.text == "|" and depth == 0:
            pipe_indexes.append(index)
    return pipe_indexes


def validate_kql(
    kql_text: str, time_range_start: datetime, time_range_end: datetime, allowed_tables: frozenset[str] | None = None, time_column: str = "TimeGenerated"
) -> HardenedQuery:
    policy = load_query_safety_policy()
    permitted_tables = policy.allowed_kql_tables if allowed_tables is None else allowed_tables
    if not kql_text or not kql_text.strip() or len(kql_text) > policy.maximum_query_characters:
        raise QueryRejectedError("The query is empty or too long.")
    tokens = _drop_trailing_semicolons(_tokenize_kql(kql_text))
    _check_kql_forbidden_content(tokens, policy)
    if _referenced_table_problems(tokens, policy, permitted_tables):
        raise QueryRejectedError(f"The query may only read these tables: {', '.join(sorted(permitted_tables))[:400]}.")

    top_level_pipes = _top_level_pipe_indexes(tokens)
    time_filter = f"| where {time_column} between ({_format_kql_datetime(time_range_start)} .. {_format_kql_datetime(time_range_end)}) "
    if top_level_pipes:
        first_pipe_offset = tokens[top_level_pipes[0]].start
        hardened_text = f"{kql_text[:first_pipe_offset].rstrip()}\n{time_filter}{kql_text[first_pipe_offset:]}"
    else:
        hardened_text = f"{kql_text.strip().rstrip(';').rstrip()}\n{time_filter}"
    hardening_steps = ["time range enforced"]
    limits_rows = any(
        index + 1 < len(tokens) and tokens[index + 1].kind == "identifier" and tokens[index + 1].text.lower() in ("take", "limit", "top", "summarize", "count")
        for index in top_level_pipes
    )
    if not limits_rows:
        hardened_text = f"{hardened_text.rstrip()}\n| take {policy.maximum_result_rows}"
        hardening_steps.append(f"row limit {policy.maximum_result_rows} added")
    return HardenedQuery("kql", hardened_text.strip(), tuple(hardening_steps))


# ── Elastic ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _clamped_size(size_value: object, maximum: int, location: str) -> int:
    if isinstance(size_value, bool) or not isinstance(size_value, int):
        raise QueryRejectedError(f"The Elastic query has a {location} that is not a whole number.")
    return max(0, min(size_value, maximum))


def _check_elastic_tree(node: Any, policy: QuerySafetyPolicy, depth: int = 0, inside_aggregations: bool = False) -> None:
    """Walk the parsed query: refuse forbidden keys anywhere and bound every aggregation size (in place)."""
    if depth > policy.elastic_maximum_json_depth:
        raise QueryRejectedError("The Elastic query is nested too deeply.")
    if isinstance(node, list):
        for item in node:
            _check_elastic_tree(item, policy, depth + 1, inside_aggregations)
    elif isinstance(node, dict):
        for key in list(node):
            value = node[key]
            if key in policy.forbidden_elastic_keys:
                raise QueryRejectedError(f"The Elastic query uses '{key}', which is not allowed (scripts, runtime fields and lookups into other indices are refused).")
            if key == "terms" and isinstance(value, dict) and any(isinstance(field_value, dict) and "index" in field_value for field_value in value.values()):
                raise QueryRejectedError("The Elastic query looks up values in another index, which is not allowed.")
            if inside_aggregations and key == "size" and not isinstance(value, (dict, list)):
                node[key] = _clamped_size(value, policy.elastic_maximum_aggregation_size, "aggregation size")
            _check_elastic_tree(value, policy, depth + 1, inside_aggregations or key in ("aggs", "aggregations"))


def validate_elastic_query(query_json_text: str, time_range_start: datetime, time_range_end: datetime, time_field: str = "@timestamp") -> HardenedQuery:
    policy = load_query_safety_policy()
    try:
        query_body = json.loads(query_json_text)
    except (json.JSONDecodeError, RecursionError) as decode_error:
        raise QueryRejectedError("The Elastic query is not valid JSON.") from decode_error
    if not isinstance(query_body, dict):
        raise QueryRejectedError("The Elastic query must be a JSON object.")
    unexpected_keys = set(query_body) - policy.allowed_elastic_top_level_keys
    if unexpected_keys:
        raise QueryRejectedError(f"Unsupported Elastic query keys: {', '.join(sorted(unexpected_keys))}.")
    _check_elastic_tree(query_body, policy)
    original_query = query_body.get("query", {"match_all": {}})
    if not isinstance(original_query, dict):
        raise QueryRejectedError("The Elastic 'query' must be a JSON object.")
    time_range_filter = {"range": {time_field: {"gte": time_range_start.isoformat(), "lte": time_range_end.isoformat()}}}
    query_body["query"] = {"bool": {"filter": [time_range_filter], "must": [original_query]}}
    query_body["size"] = _clamped_size(query_body.get("size", policy.elastic_default_size), policy.maximum_result_rows, "size")
    return HardenedQuery("elastic_dsl", json.dumps(query_body), ("time range enforced", "size bounded"))


def validate_elastic_index_pattern(index_pattern: str) -> str:
    """The index pattern goes into the request path, so it may not be able to change the path, add a query or reach another cluster."""
    policy = load_query_safety_policy()
    if (
        not isinstance(index_pattern, str) or not index_pattern or len(index_pattern) > policy.elastic_maximum_index_pattern_characters
        or not ELASTIC_INDEX_PATTERN_CHARACTERS.fullmatch(index_pattern) or ".." in index_pattern
        or any(not component or component.startswith("_") for component in index_pattern.split(","))
    ):
        raise QueryRejectedError(
            "The Elastic index pattern is not valid. Use letters, digits, '-', '_', '.', '*' and commas only; "
            "names may not start with '_' and '..' is not allowed."
        )
    return index_pattern


# ── Splunk ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
_SPL_INDEX_TERM = re.compile(r"\bindex\s*(?P<operator>!=|::|=)\s*(?P<value>\"_*\"|[^\s()]+)?", re.IGNORECASE)
_SPL_INDEX_IN_LIST = re.compile(r"\bindex\s+in\b", re.IGNORECASE)
_SPL_TIME_TERM = re.compile(r"\b(?:earliest|latest)\s*=\s*(?:\"_*\"|[^\s()]+)", re.IGNORECASE)
_SPL_FIRST_WORD = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)")


def configured_splunk_index(query_scope: Mapping[str, Any] | None) -> str | None:
    """The one index a log source may search, or None when the source has no plain index name (wildcards are not accepted)."""
    index_name = (query_scope or {}).get("index") or (query_scope or {}).get("index_pattern")
    return index_name if isinstance(index_name, str) and SPLUNK_INDEX_NAME_PATTERN.fullmatch(index_name) else None


def describe_query_limits(
    query_language: str, query_scope: Mapping[str, Any] | None = None, connection_configuration: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """What a generated query may use for one log source, taken from the same policy and scope the validators enforce.

    It goes into the query-writing prompts so the model works from real tables, indices and field names instead of guessing them.
    """
    policy = load_query_safety_policy()
    scope, configuration = query_scope or {}, connection_configuration or {}
    if query_language == "kql":
        return {"queryLanguage": "kql", "allowedTables": sorted(policy.allowed_kql_tables)}
    if query_language == "spl":
        return {"queryLanguage": "spl", "index": configured_splunk_index(scope), "allowedCommands": sorted(policy.allowed_spl_commands)}
    limits: dict[str, Any] = {"queryLanguage": "elastic_dsl", "indexPattern": scope.get("index_pattern") or configuration.get("index_pattern"), "allowedTopLevelKeys": sorted(policy.allowed_elastic_top_level_keys)}
    for limit_name, configuration_key in (("timeField", "time_field"), ("serviceField", "service_field"), ("levelField", "level_field")):
        if configuration.get(configuration_key) or scope.get(configuration_key):
            limits[limit_name] = configuration.get(configuration_key) or scope.get(configuration_key)
    return limits


def _split_spl_commands(spl_text: str) -> list[str]:
    """Split on pipes that are outside double-quoted strings. Anything that could make the quoting ambiguous is rejected."""
    commands: list[str] = []
    current: list[str] = []
    in_quotes = False
    position = 0
    while position < len(spl_text):
        character = spl_text[position]
        if character == "`":
            raise QueryRejectedError("Splunk macros (backticks) are not allowed.")
        if not character.isprintable() and character not in "\t\r\n":
            raise QueryRejectedError("The Splunk query contains a control character.")
        if not in_quotes and not character.isascii():
            raise QueryRejectedError("The Splunk query contains a character that Splunk does not use outside quoted text.")
        if in_quotes and character == "\\":
            current.append(spl_text[position : position + 2])
            position += 2
            continue
        if not in_quotes and character == "\\":
            raise QueryRejectedError("The Splunk query has a backslash outside quoted text.")
        if character == '"':
            in_quotes = not in_quotes
        elif not in_quotes and character in "[]":
            raise QueryRejectedError("Splunk subsearches (square brackets) are not allowed.")
        elif not in_quotes and character == "|":
            commands.append("".join(current))
            current = []
            position += 1
            continue
        current.append(character)
        position += 1
    if in_quotes:
        raise QueryRejectedError("A quoted text value in the Splunk query is not closed.")
    commands.append("".join(current))
    return commands


def _masked_outside_quotes(command_text: str) -> str:
    """Same length as the input, with the inside of every double-quoted string replaced by underscores."""
    masked: list[str] = []
    in_quotes = False
    position = 0
    while position < len(command_text):
        character = command_text[position]
        if in_quotes and character == "\\":
            masked.append("__")
            position += 2
            continue
        if character == '"':
            in_quotes = not in_quotes
            masked.append(character)
        else:
            masked.append("_" if in_quotes else character)
        position += 1
    return "".join(masked)


def _remove_spans(command_text: str, spans: list[tuple[int, int]]) -> str:
    for span_start, span_end in sorted(spans, reverse=True):
        command_text = command_text[:span_start] + " " + command_text[span_end:]
    return command_text


def _strip_index_and_time_terms(command_text: str, required_index: str) -> str:
    """Remove ``index=`` (only the configured index or ``*`` is accepted) and earliest / latest terms from one command."""
    masked = _masked_outside_quotes(command_text)
    if _SPL_INDEX_IN_LIST.search(masked):
        raise QueryRejectedError(f"The Splunk query may only search the index '{required_index}'; index lists are not supported.")
    spans: list[tuple[int, int]] = []
    for term in _SPL_INDEX_TERM.finditer(masked):
        value = command_text[term.start("value") : term.end("value")].strip('"') if term.group("value") else ""
        if term.group("operator") != "=" or value not in (required_index, "*"):
            raise QueryRejectedError(f"The Splunk query may only search the index '{required_index}'.")
        spans.append(term.span())
    spans.extend(term.span() for term in _SPL_TIME_TERM.finditer(masked))
    return _remove_spans(command_text, spans)


def _bounds_text(required_index: str, time_range_start: datetime, time_range_end: datetime) -> str:
    return f"index={required_index} earliest={int(time_range_start.timestamp())} latest={int(time_range_end.timestamp())}"


def _bound_tstats_command(command_text: str, bounds: str) -> str:
    """Put the index and time bounds into the WHERE clause of a tstats command (before BY when it has none)."""
    masked = _masked_outside_quotes(command_text)
    where_match = re.search(r"\bwhere\b", masked, re.IGNORECASE)
    if where_match:
        remainder = command_text[where_match.end() :].strip()
        return f"{command_text[: where_match.end()].rstrip()} {bounds}{(' ' + remainder) if remainder else ''}"
    by_match = re.search(r"\bby\b", masked, re.IGNORECASE)
    if by_match:
        return f"{command_text[: by_match.start()].rstrip()} where {bounds} {command_text[by_match.start() :].strip()}"
    return f"{command_text.rstrip()} where {bounds}"


def validate_spl(spl_text: str, time_range_start: datetime, time_range_end: datetime, required_index: str | None = None) -> HardenedQuery:
    policy = load_query_safety_policy()
    if not spl_text or not spl_text.strip() or len(spl_text) > policy.maximum_query_characters:
        raise QueryRejectedError("The query is empty or too long.")
    if required_index is None:
        raise QueryRejectedError("This Splunk log source has no index configured, so Keigan cannot limit the search to it. Ask an application admin to set the index on the log source.")
    commands = [command.strip() for command in _split_spl_commands(spl_text.strip())]
    has_generating_command = spl_text.lstrip().startswith("|")
    if has_generating_command:
        commands = commands[1:]
    else:
        first_word = _SPL_FIRST_WORD.match(commands[0])
        if first_word is None or first_word.group(1).lower() != "search":
            commands[0] = f"search {commands[0]}"
    command_words: list[str] = []
    for command in commands:
        word_match = _SPL_FIRST_WORD.match(command)
        command_word = word_match.group(1).lower() if word_match else ""
        if not command_word:
            raise QueryRejectedError("The Splunk query has an empty command.")
        if command_word not in policy.allowed_spl_commands:
            raise QueryRejectedError(f"The Splunk command '{command_word}' is not allowed. Allowed commands: {', '.join(sorted(policy.allowed_spl_commands))}.")
        command_words.append(command_word)
    if has_generating_command and command_words[0] not in policy.allowed_spl_generating_commands:
        raise QueryRejectedError(f"A Splunk query may not start with '| {command_words[0]}'.")
    commands = [_strip_index_and_time_terms(command, required_index) for command in commands]
    commands = [command.strip() for command in commands]
    bounds = _bounds_text(required_index, time_range_start, time_range_end)
    if command_words[0] == "tstats":
        commands[0] = _bound_tstats_command(commands[0], bounds)
    else:
        search_terms = commands[0][len("search") :].strip()
        commands[0] = f"search {bounds}{(' ' + search_terms) if search_terms else ''}"
    hardened_text = " | ".join(commands)
    if has_generating_command:
        hardened_text = f"| {hardened_text}"
    hardening_steps = ["index and time range enforced"]
    if not any(command_word in policy.spl_row_limiting_commands for command_word in command_words):
        hardened_text += f" | head {policy.maximum_result_rows}"
        hardening_steps.append(f"row limit {policy.maximum_result_rows} added")
    return HardenedQuery("spl", hardened_text, tuple(hardening_steps))


def validate_generated_query(
    query_language: str, query_text: str, time_range_start: datetime, time_range_end: datetime, query_scope: Mapping[str, Any] | None = None, **options: object
) -> HardenedQuery:
    """Validate and harden a generated query. ``query_scope`` is the log source's scope (it names the one Splunk index that may be searched)."""
    if query_language == "kql":
        return validate_kql(query_text, time_range_start, time_range_end, **options)  # type: ignore[arg-type]
    if query_language == "elastic_dsl":
        return validate_elastic_query(query_text, time_range_start, time_range_end, **options)  # type: ignore[arg-type]
    if query_language == "spl":
        return validate_spl(query_text, time_range_start, time_range_end, required_index=configured_splunk_index(query_scope))
    raise QueryRejectedError(f"Keigan cannot run generated {query_language} queries yet.")
