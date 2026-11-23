"""The burn-rate thresholds and windows of an SLO (pure; no database).

An SLO stores its own multiwindow policy (``burn_rate_policy_json``, written when an SLI proposal is accepted): for each alert severity a burn rate, a long window and a short window. An
alert fires when both windows burn faster than the threshold. A missing or unusable policy falls back to the default pair rather than silencing the alert: a typo in a stored policy must
never turn the SLO's paging off.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

MAXIMUM_BURN_RATE = 1000.0
MAXIMUM_WINDOW = timedelta(days=30)  # no SLO rolls longer than this
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


@dataclass(frozen=True)
class BurnPolicy:
    burn_rate: float
    long_window: timedelta
    short_window: timedelta


DEFAULT_POLICIES: dict[str, BurnPolicy] = {
    "page": BurnPolicy(14.4, timedelta(hours=1), timedelta(minutes=5)),
    "ticket": BurnPolicy(6.0, timedelta(hours=6), timedelta(minutes=30)),
}


def parse_iso_duration(text: object) -> timedelta | None:
    """An ISO 8601 duration of days, hours, minutes and seconds (``PT5M``, ``P1DT12H``); None when it is anything else or zero."""
    if not isinstance(text, str):
        return None
    match = _DURATION.match(text)
    if match is None or not any(group is not None for group in match.groups()):
        return None
    days, hours, minutes, seconds = (int(group) if group else 0 for group in match.groups())
    duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return duration if duration > timedelta(0) else None


def _usable(entry: object) -> BurnPolicy | None:
    if not isinstance(entry, Mapping):
        return None
    burn_rate = entry.get("burnRate")
    long_window, short_window = parse_iso_duration(entry.get("longWindow")), parse_iso_duration(entry.get("shortWindow"))
    if isinstance(burn_rate, bool) or not isinstance(burn_rate, (int, float)) or not 0 < burn_rate <= MAXIMUM_BURN_RATE:
        return None
    if long_window is None or short_window is None or short_window >= long_window or long_window > MAXIMUM_WINDOW:
        return None
    return BurnPolicy(float(burn_rate), long_window, short_window)


def policy_for(stored: Mapping[str, Any] | None, severity: str) -> BurnPolicy:
    """The policy of ``severity`` ("page" or "ticket") from an SLO's stored policy, or the default when it is missing or unusable."""
    return _usable((stored or {}).get(severity)) or DEFAULT_POLICIES[severity]
