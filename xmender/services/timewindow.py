"""Weekly time windows ("weekdays 09:00-17:00") in a user's time zone."""

from __future__ import annotations

import re
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def parse_hhmm(value: str) -> time:
    """Raises ValueError for anything but HH:MM (24 h)."""
    m = _HHMM.match(str(value or "").strip())
    if not m:
        raise ValueError("times must be HH:MM (24-hour).")
    return time(int(m.group(1)), int(m.group(2)))


def in_window(now: datetime, days: list[int], start: time, end: time, zone: str) -> tuple[bool, str]:
    """Whether aware `now` falls in the window, plus the local time as text.

    `days` are weekday numbers (Mon=0). start == end means the whole day.
    When end < start the window runs past midnight; it then belongs to the
    day it started on, so "Fri 22:00-02:00" includes Saturday 01:00."""
    local = now.astimezone(ZoneInfo(zone))
    t, day = local.time().replace(second=0, microsecond=0), local.weekday()
    label = f"{DAY_NAMES[day]} {local:%H:%M} {zone}"
    if start == end:
        return day in days, label
    if start < end:
        return day in days and start <= t < end, label
    return (day in days and t >= start) or ((day - 1) % 7 in days and t < end), label
