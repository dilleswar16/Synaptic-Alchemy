"""The one error type of the demo data SQL generator. Messages say what is wrong, where, and what to change."""

from __future__ import annotations


class DemoDataSqlError(Exception):
    """The seed, the entities or the declared file plan cannot be turned into safe demo data SQL."""
