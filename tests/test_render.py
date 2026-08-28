import struct
from datetime import datetime, timezone

from nonebot_plugin_how_to_cook.config import Config
from nonebot_plugin_how_to_cook.content import Document, Section
from nonebot_plugin_how_to_cook.render import CardRenderer, png_dimensions, sanitize_html_fragment


def test_html_sanitizer_removes_active_content() -> None:
    value = sanitize_html_fragment(
        '<p onclick="bad()">安全</p><script>alert(1)</script>'
        '<img src="javascript:bad" alt="x"><a href="https://example.com">链接</a>'
    )
    assert "安全" in value
    assert "script" not in value
    assert "alert" not in value
    assert "onclick" not in value
    assert "javascript" not in value
    assert "https://example.com" in value


def test_card_builds_markdown_with_dark_theme_and_cover() -> None:
    renderer = CardRenderer(Config())
    document = Document(
        "番茄炒蛋",
        description="家常快手菜",
        stats=[("难度", "★★")],
        sections=[Section("步骤", "1. 炒鸡蛋")],
        cover_url="/assets/dish.jpg",
        asset_base_url="http://cook.test",
    )
    html, theme = renderer.build_html(
        document,
        now=datetime(2026, 8, 28, 15, 30, tzinfo=timezone.utc),
    )
    assert theme == "dark"
    assert "番茄炒蛋" in html
    assert "<h2>步骤</h2>" in html
    assert "http://cook.test/" in html
    assert "/assets/dish.jpg" in html


def test_png_dimensions() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 920, 15001)
    assert png_dimensions(png) == (920, 15001)
    assert png_dimensions(b"not png") is None
