from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import ThemeMode


class ThemeConfigurationError(ValueError):
    pass


def parse_clock(value: str) -> int:
    """Convert an ``HH:MM`` clock value into minutes since midnight."""

    pieces = value.strip().split(":")
    if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
        raise ThemeConfigurationError(f"无效时间 {value!r}，应使用 HH:MM")
    hour, minute = (int(piece) for piece in pieces)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ThemeConfigurationError(f"无效时间 {value!r}，应使用 HH:MM")
    return hour * 60 + minute


def is_dark_time(current: int, start: int, end: int) -> bool:
    """Return whether a minute falls inside a possibly cross-midnight range."""

    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


def resolve_theme(
    mode: ThemeMode,
    *,
    timezone: str,
    dark_start: str,
    dark_end: str,
    now: datetime | None = None,
) -> str:
    if mode in {"light", "dark"}:
        return mode
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ThemeConfigurationError(f"未知时区：{timezone}") from exc
    localized = now.astimezone(zone) if now is not None else datetime.now(zone)
    current = localized.hour * 60 + localized.minute
    return (
        "dark" if is_dark_time(current, parse_clock(dark_start), parse_clock(dark_end)) else "light"
    )
