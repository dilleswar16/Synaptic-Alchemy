"""Renders Python values as T-SQL (Azure SQL) literals. The COLUMN TYPE from the entity metadata decides how, not the Python type of the value."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, Integer, String, TypeDecorator
from sqlalchemy.types import TypeEngine

from demo_data_sql.demo_data_errors import DemoDataSqlError

SQL_SERVER_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"  # DATETIME2(6): language independent
SQLCMD_COMMAND_LINE = re.compile(r"^\s*(go(\s+\d+)?\s*|:.*)$", re.IGNORECASE | re.MULTILINE)  # a batch separator or a :r style command at a line start
SQLCMD_VARIABLE = "$("


def _column_label(column: Column) -> str:
    return f"{column.table.name}.{column.name}"


def _resolve_type(column: Column) -> TypeEngine[Any]:
    """The underlying SQL type: ``UtcDateTime`` and other type decorators render like the type they wrap."""
    resolved_type = column.type
    while isinstance(resolved_type, TypeDecorator):
        resolved_type = resolved_type.impl_instance
    return resolved_type


def _reject(column: Column, expectation: str, value: Any) -> DemoDataSqlError:
    return DemoDataSqlError(f"Column {_column_label(column)} expects {expectation} but the seed holds a {type(value).__name__} ({value!r:.60}). Fix the seed or the entity.")


def _render_text(text: str, column: Column) -> str:
    if "\x00" in text or SQLCMD_VARIABLE in text or SQLCMD_COMMAND_LINE.search(text):
        raise DemoDataSqlError(
            f"A text value for {_column_label(column)} contains a NUL character, '$(' or a line that sqlcmd would run as a command (GO or :...). "
            f"sqlcmd would corrupt the script, so change the seed text: {text!r:.80}"
        )
    return "N'" + text.replace("'", "''") + "'"


def _render_boolean(value: Any, column: Column) -> str:
    if isinstance(value, bool) or (isinstance(value, int) and value in (0, 1)):
        return "1" if value else "0"
    raise _reject(column, "a boolean (true, false, 0 or 1)", value)


def _render_integer(value: Any, column: Column) -> str:
    if isinstance(value, int):  # a bool is an int; an Integer column holding True means 1
        return str(int(value))
    raise _reject(column, "an integer", value)


def _render_float(value: Any, column: Column) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _reject(column, "a number", value)
    if isinstance(value, float) and not math.isfinite(value):
        raise DemoDataSqlError(f"Column {_column_label(column)} holds {value}; SQL Server cannot store NaN or infinity in a float column. Fix the seed so it writes a real number or NULL.")
    return repr(value) if isinstance(value, float) else str(value)


def _render_datetime(value: Any, column: Column) -> str:
    if not isinstance(value, datetime):
        raise _reject(column, "a datetime", value)
    utc_value = value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value  # timestamps are UTC; naive ones already are
    return f"'{utc_value.strftime(SQL_SERVER_DATETIME_FORMAT)}'"


def _render_date(value: Any, column: Column) -> str:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise _reject(column, "a date (without a time)", value)
    return f"'{value.isoformat()}'"


def _render_json(value: Any, column: Column) -> str:
    try:
        return _render_text(json.dumps(value, ensure_ascii=False, allow_nan=False), column)
    except (TypeError, ValueError) as problem:
        raise DemoDataSqlError(f"Column {_column_label(column)} (JSON) holds a value that is not valid JSON text: {problem}.") from problem


def _render_string(value: Any, column: Column) -> str:
    if not isinstance(value, str):
        raise _reject(column, "text", value)
    return _render_text(value, column)


# Order matters: a Text column is also a String; Boolean and the numeric types are separate families.
_RENDERERS_BY_TYPE: tuple[tuple[type, Any], ...] = (
    (Boolean, _render_boolean),
    (Integer, _render_integer),
    (Float, _render_float),
    (DateTime, _render_datetime),
    (Date, _render_date),
    (JSON, _render_json),
    (String, _render_string),  # Text is a String subclass
)


def render_literal(value: Any, column: Column) -> str:
    """The T-SQL literal for ``value`` in ``column``; raises ``DemoDataSqlError`` for anything SQL Server cannot take as is."""
    column_type = _resolve_type(column)
    for sql_type, renderer in _RENDERERS_BY_TYPE:
        if isinstance(column_type, sql_type):
            return "NULL" if value is None else renderer(value, column)
    raise DemoDataSqlError(
        f"Column {_column_label(column)} has type {type(column_type).__name__}, which is not supported by the demo data generator. "
        "Add a renderer in scripts/demo_data_sql/sql_literals.py or exclude the table."
    )
