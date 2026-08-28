from datetime import datetime, timezone

import pytest

from nonebot_plugin_how_to_cook.themes import (
    ThemeConfigurationError,
    is_dark_time,
    parse_clock,
    resolve_theme,
)


def test_clock_and_cross_midnight_range() -> None:
    assert parse_clock("23:00") == 1380
    assert is_dark_time(parse_clock("23:30"), parse_clock("23:00"), parse_clock("08:00"))
    assert is_dark_time(parse_clock("07:59"), parse_clock("23:00"), parse_clock("08:00"))
    assert not is_dark_time(parse_clock("08:00"), parse_clock("23:00"), parse_clock("08:00"))


def test_equal_range_means_always_dark() -> None:
    assert is_dark_time(12 * 60, parse_clock("08:00"), parse_clock("08:00"))


def test_resolve_theme_uses_configured_timezone() -> None:
    # 15:30 UTC is 23:30 in Shanghai.
    now = datetime(2026, 8, 28, 15, 30, tzinfo=timezone.utc)
    assert (
        resolve_theme(
            "auto",
            timezone="Asia/Shanghai",
            dark_start="23:00",
            dark_end="08:00",
            now=now,
        )
        == "dark"
    )
    assert (
        resolve_theme(
            "light",
            timezone="Invalid/Zone",
            dark_start="bad",
            dark_end="bad",
            now=now,
        )
        == "light"
    )


@pytest.mark.parametrize("value", ["24:00", "7", "aa:bb", "10:60"])
def test_invalid_clock(value: str) -> None:
    with pytest.raises(ThemeConfigurationError):
        parse_clock(value)
