"""Time helpers. All times inside Keigan are timezone-aware UTC; conversion to local time happens in the UI."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_ISO_DURATION_PATTERN = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", re.IGNORECASE)


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(timestamp: datetime | None) -> datetime | None:
    if timestamp is None:
        return None
    return timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp.astimezone(UTC)


def parse_iso_duration(duration_text: str) -> timedelta:
    """Parse ISO 8601 durations such as ``PT17H`` or ``P7D``."""
    duration_match = _ISO_DURATION_PATTERN.match(duration_text.strip())
    if not duration_match:
        raise ValueError(f"Not an ISO 8601 duration: {duration_text}")
    days, hours, minutes, seconds = (int(part) if part else 0 for part in duration_match.groups())
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def floor_to_interval(timestamp: datetime, interval_minutes: int) -> datetime:
    utc_timestamp = ensure_utc(timestamp) or utc_now()
    minutes_since_midnight = utc_timestamp.hour * 60 + utc_timestamp.minute
    floored_minutes = minutes_since_midnight - minutes_since_midnight % interval_minutes
    return utc_timestamp.replace(hour=floored_minutes // 60, minute=floored_minutes % 60, second=0, microsecond=0)


def iterate_windows(start_time: datetime, end_time: datetime, interval_minutes: int) -> list[datetime]:
    window_starts: list[datetime] = []
    current_window_start = floor_to_interval(start_time, interval_minutes)
    while current_window_start < end_time:
        window_starts.append(current_window_start)
        current_window_start += timedelta(minutes=interval_minutes)
    return window_starts


def to_iso_string(timestamp: datetime | None) -> str | None:
    return ensure_utc(timestamp).isoformat().replace("+00:00", "Z") if timestamp else None


def hour_of_week(timestamp: datetime) -> int:
    utc_timestamp = ensure_utc(timestamp) or utc_now()
    return utc_timestamp.weekday() * 24 + utc_timestamp.hour
