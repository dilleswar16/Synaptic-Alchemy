"""Risk level of a command that the AI proposes: ``low`` (read-only), ``medium`` (changes state) or ``high`` (destructive or broad).

The command is tokenised, the verb is found wherever it sits (after flags such as ``-n prod``), wrapper programs and shell
operators are looked through, and SQL is read statement by statement. A command is low only when it is on a read-only list;
anything unknown is at least medium. The rules live in ``resources/catalogs/command_risk_rules.yaml``.
"""

from __future__ import annotations

import ntpath
import re
import shlex
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

from keigan.ai.prompt_safety import strip_invisible_characters
from keigan.config.settings import RESOURCES_DIRECTORY

RISK_RANK = {"low": 0, "medium": 1, "high": 2}
_STATEMENT_SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "|&", ";;", "(", ")"})
_SQL_COMMENT_PATTERN = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_FIRST_WORD_PATTERN = re.compile(r"\s*([A-Za-z_]+)")
_WHERE_PATTERN = re.compile(r"\bwhere\b", re.IGNORECASE)
_ENVIRONMENT_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


@dataclass(frozen=True)
class _Family:
    executables: frozenset[str]
    verb_position: str
    value_flags: frozenset[str]
    default_risk: str
    verb_risk: dict[str, Any]
    verb_prefix_risk: dict[str, str]


@dataclass(frozen=True)
class _Rules:
    wrapper_executables: frozenset[str]
    shell_executables: frozenset[str]
    pipe_into_interpreters: frozenset[str]
    read_only_executables: frozenset[str]
    state_changing_arguments: dict[str, frozenset[str]]
    high_risk_executables: frozenset[str]
    read_only_prefixes: tuple[str, ...]
    high_risk_prefixes: tuple[str, ...]
    high_risk_arguments: frozenset[str]
    high_risk_argument_pairs: tuple[tuple[str, str], ...]
    families_by_executable: dict[str, _Family]
    sql_mode_keywords: frozenset[str]
    sql_read_only: frozenset[str]
    sql_high: frozenset[str]
    sql_client_executables: frozenset[str]
    sql_tautology_pattern: re.Pattern[str]


@lru_cache
def _load_rules() -> _Rules:
    catalog = yaml.safe_load((RESOURCES_DIRECTORY / "catalogs" / "command_risk_rules.yaml").read_text(encoding="utf-8"))
    families_by_executable: dict[str, _Family] = {}
    for family_entry in catalog["families"].values():
        family = _Family(
            executables=frozenset(family_entry["executables"]), verb_position=family_entry["verb_position"], value_flags=frozenset(family_entry["value_flags"]),
            default_risk=family_entry["default_risk"], verb_risk=family_entry["verb_risk"], verb_prefix_risk=family_entry.get("verb_prefix_risk", {}),
        )
        families_by_executable.update({executable: family for executable in family.executables})
    sql_entry = catalog["sql"]
    return _Rules(
        wrapper_executables=frozenset(catalog["wrapper_executables"]), shell_executables=frozenset(catalog["shell_executables"]),
        pipe_into_interpreters=frozenset(catalog["pipe_into_interpreters"]), read_only_executables=frozenset(catalog["read_only_executables"]),
        state_changing_arguments={executable: frozenset(arguments) for executable, arguments in catalog["state_changing_arguments"].items()},
        high_risk_executables=frozenset(catalog["high_risk_executables"]), read_only_prefixes=tuple(catalog["read_only_executable_prefixes"]),
        high_risk_prefixes=tuple(catalog["high_risk_executable_prefixes"]), high_risk_arguments=frozenset(catalog["high_risk_arguments"]),
        high_risk_argument_pairs=tuple((first, second) for first, second in catalog["high_risk_argument_pairs"]), families_by_executable=families_by_executable,
        sql_mode_keywords=frozenset(sql_entry["mode_keywords"]), sql_read_only=frozenset(sql_entry["read_only"]), sql_high=frozenset(sql_entry["high"]), sql_client_executables=frozenset(sql_entry["client_executables"]),
        sql_tautology_pattern=re.compile(sql_entry["tautology_pattern"]),
    )


def _highest(first_risk: str, second_risk: str) -> str:
    return first_risk if RISK_RANK[first_risk] >= RISK_RANK[second_risk] else second_risk


def classify_command_risk(command_text: str) -> str:
    """Return ``high``, ``medium`` or ``low`` for a command, a pipeline or a multi-line block of commands."""
    cleaned_text = strip_invisible_characters(command_text or "").strip()
    if not cleaned_text:
        return "low"
    if _starts_with_sql(cleaned_text, _load_rules()):
        return _classify_sql(cleaned_text)
    risk_level = "low"
    for command_line in cleaned_text.replace("\\\n", " ").splitlines():
        stripped_line = command_line.strip()
        if stripped_line and not stripped_line.startswith(("#", "//")):
            risk_level = _highest(risk_level, _classify_shell_line(stripped_line))
    return risk_level


def _starts_with_sql(text: str, rules: _Rules) -> bool:
    first_word_match = _FIRST_WORD_PATTERN.match(text)
    return first_word_match is not None and first_word_match.group(1).lower() in rules.sql_mode_keywords


# ── Shell ──────────────────────────────────────────────────────────────────────

def _tokenize(command_line: str) -> list[str]:
    lexer = shlex.shlex(command_line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:  # unbalanced quotes: a plain split still exposes the verb
        return command_line.split()


def _split_simple_commands(tokens: list[str]) -> tuple[list[list[str]], bool]:
    """Simple commands separated by pipes, ``&&``, ``;`` and so on, and whether any output is redirected into a file."""
    simple_commands: list[list[str]] = [[]]
    redirects_to_file = False
    token_index = 0
    while token_index < len(tokens):
        token = tokens[token_index]
        if token in _STATEMENT_SEPARATORS:
            simple_commands.append([])
        elif ">" in token and set(token) <= set("<>&|0123456789"):
            redirect_target = tokens[token_index + 1] if token_index + 1 < len(tokens) else ""
            if redirect_target not in ("/dev/null", "&1", "&2", "1", "2", "nul") and not token.endswith("&"):
                redirects_to_file = True
            token_index += 1
        else:
            simple_commands[-1].append(token)
        token_index += 1
    return [simple_command for simple_command in simple_commands if simple_command], redirects_to_file


def _executable_name(token: str) -> str:
    return ntpath.basename(token.replace("/", "\\")).lower().removesuffix(".exe")


def _classify_shell_line(command_line: str) -> str:
    rules = _load_rules()
    simple_commands, redirects_to_file = _split_simple_commands(_tokenize(command_line))
    risk_level = "medium" if redirects_to_file else "low"
    for command_position, simple_command in enumerate(simple_commands):
        command_tokens = _unwrap(simple_command, rules)
        if command_position > 0 and command_tokens and _executable_name(command_tokens[0]) in rules.pipe_into_interpreters:
            risk_level = _highest(risk_level, "high")  # whatever was piped in gets executed
        risk_level = _highest(risk_level, _classify_command_tokens(command_tokens, rules))
    return risk_level


def _skip_assignments(simple_command: list[str]) -> list[str]:
    start_index = 0
    while start_index < len(simple_command) and _ENVIRONMENT_ASSIGNMENT_PATTERN.match(simple_command[start_index]):
        start_index += 1
    return simple_command[start_index:]


def _is_known_executable(token: str, rules: _Rules) -> bool:
    name = _executable_name(token)
    return (
        name in rules.families_by_executable or name in rules.read_only_executables or name in rules.high_risk_executables
        or name in rules.shell_executables or name in rules.sql_client_executables
    )


def _unwrap(simple_command: list[str], rules: _Rules) -> list[str]:
    """Drop ``sudo``, ``env``, ``xargs`` and similar wrappers (and their options) so the wrapped command is classified."""
    remaining = _skip_assignments(simple_command)
    while remaining and _executable_name(remaining[0]) in rules.wrapper_executables:
        after_wrapper = _skip_assignments(remaining[1:])
        known_position = next((position for position, token in enumerate(after_wrapper) if _is_known_executable(token, rules)), None)
        if known_position is not None:
            remaining = after_wrapper[known_position:]
        else:  # unknown wrapped command: skip the wrapper's options and a numeric argument such as ``timeout 30``
            positional_tokens = [token for token in after_wrapper if not token.startswith("-")]
            remaining = positional_tokens[1:] if positional_tokens and positional_tokens[0].isdigit() else positional_tokens
    return remaining


def _classify_command_tokens(command_tokens: list[str], rules: _Rules) -> str:
    if not command_tokens:
        return "low"
    executable = _executable_name(command_tokens[0])
    argument_tokens = command_tokens[1:]
    if executable in rules.shell_executables:
        return _highest("medium", _classify_embedded_command(argument_tokens))
    if executable in rules.sql_client_executables:
        return _highest("medium", _classify_embedded_sql(argument_tokens))
    if executable in rules.families_by_executable:
        base_risk = _classify_family_command(rules.families_by_executable[executable], argument_tokens)
    elif executable in rules.high_risk_executables or executable.startswith(rules.high_risk_prefixes):
        return "high"
    elif executable in rules.read_only_executables or executable.startswith(rules.read_only_prefixes):
        changing_arguments = rules.state_changing_arguments.get(executable, frozenset())
        base_risk = "medium" if any(argument in changing_arguments or argument.split("=", 1)[0] in changing_arguments for argument in argument_tokens) else "low"
    else:
        base_risk = "medium"
    if base_risk != "low" and _has_high_risk_argument(argument_tokens, rules):
        return "high"
    return base_risk


def _has_high_risk_argument(argument_tokens: list[str], rules: _Rules) -> bool:
    lowered_tokens = [token.lower() for token in argument_tokens]
    if any(token in rules.high_risk_arguments for token in lowered_tokens):
        return True
    return any(first == lowered_tokens[position] and position + 1 < len(lowered_tokens) and lowered_tokens[position + 1] == second for first, second in rules.high_risk_argument_pairs for position in range(len(lowered_tokens)))


def _classify_embedded_command(argument_tokens: list[str]) -> str:
    """``bash -c "…"`` and ``pwsh -Command "…"``: classify the command string that is passed in."""
    for position, token in enumerate(argument_tokens):
        if token.lower() in ("-c", "-command", "/c", "-lc") and position + 1 < len(argument_tokens):
            return classify_command_risk(argument_tokens[position + 1])
    return "medium"


def _classify_embedded_sql(argument_tokens: list[str]) -> str:
    risk_level = "low"
    for token in argument_tokens:
        if _starts_with_sql(token, _load_rules()):
            risk_level = _highest(risk_level, _classify_sql(token))
    return risk_level


def _classify_family_command(family: _Family, argument_tokens: list[str]) -> str:
    positional_tokens = _positional_tokens(family, argument_tokens)
    if not positional_tokens:
        return "low"  # only flags such as --help or --version
    verb = positional_tokens[-1] if family.verb_position == "last_positional_before_flags" else positional_tokens[0]
    verb_entry = family.verb_risk.get(verb.lower())
    if isinstance(verb_entry, dict):
        following_tokens = [token for token in argument_tokens[argument_tokens.index(verb) + 1:] if not token.startswith("-")]
        sub_verb = following_tokens[0].lower() if following_tokens else ""
        return verb_entry.get(sub_verb, verb_entry["default"])
    if isinstance(verb_entry, str):
        return verb_entry
    for prefix, prefix_risk in family.verb_prefix_risk.items():
        if verb.lower().startswith(prefix):
            return prefix_risk
    return family.default_risk


def _positional_tokens(family: _Family, argument_tokens: list[str]) -> list[str]:
    """Positional words (verbs and their subjects) with flags and flag values skipped; for az only the run before the first flag."""
    positional_tokens: list[str] = []
    token_index = 0
    while token_index < len(argument_tokens):
        token = argument_tokens[token_index]
        if token.startswith("-"):
            if family.verb_position == "last_positional_before_flags" and positional_tokens:
                break
            if token in family.value_flags and "=" not in token:
                token_index += 1
        else:
            positional_tokens.append(token)
            if family.verb_position == "first_positional":
                break
        token_index += 1
    return positional_tokens


# ── SQL ────────────────────────────────────────────────────────────────────────

def _classify_sql(sql_text: str) -> str:
    rules = _load_rules()
    uncommented_text = _SQL_COMMENT_PATTERN.sub(" ", sql_text)
    risk_level = "low"
    if "xp_cmdshell" in uncommented_text.lower():
        return "high"
    for statement in uncommented_text.split(";"):
        first_word_match = _FIRST_WORD_PATTERN.match(statement)
        if not first_word_match:
            continue
        keyword = first_word_match.group(1).lower()
        if keyword in rules.sql_high:
            risk_level = _highest(risk_level, "high")
        elif keyword in rules.sql_read_only:
            risk_level = _highest(risk_level, "medium" if re.search(r"\binto\b", statement, re.IGNORECASE) and keyword == "select" else "low")
        elif keyword in ("delete", "update"):
            has_real_condition = bool(_WHERE_PATTERN.search(statement)) and not rules.sql_tautology_pattern.search(statement + ";")
            risk_level = _highest(risk_level, "medium" if has_real_condition else "high")
        else:
            risk_level = _highest(risk_level, "medium")
    return risk_level
