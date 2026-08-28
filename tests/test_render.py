import importlib
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from nonebot_plugin_how_to_cook.config import Config
from nonebot_plugin_how_to_cook.content import Document, Section, recipe_list_document
from nonebot_plugin_how_to_cook.render import CardRenderer, png_dimensions, sanitize_html_fragment


def test_card_renderer_supports_vendored_package_identity(monkeypatch) -> None:
    package_root = Path(__file__).resolve().parents[1] / "nonebot_plugin_how_to_cook"
    vendored_name = "src.plugins.nonebot_plugin_how_to_cook"

    src_package = ModuleType("src")
    src_package.__path__ = []  # type: ignore[attr-defined]
    plugins_package = ModuleType("src.plugins")
    plugins_package.__path__ = []  # type: ignore[attr-defined]
    vendored_package = ModuleType(vendored_name)
    vendored_package.__path__ = [str(package_root)]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src", src_package)
    monkeypatch.setitem(sys.modules, "src.plugins", plugins_package)
    monkeypatch.setitem(sys.modules, vendored_name, vendored_package)

    vendored_render = importlib.import_module(f"{vendored_name}.render")
    vendored_config = importlib.import_module(f"{vendored_name}.config")
    original_import_module = importlib.import_module

    def reject_top_level_package(name: str, package: str | None = None):
        if name == "nonebot_plugin_how_to_cook":
            raise ModuleNotFoundError(name)
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", reject_top_level_package)
    renderer = vendored_render.CardRenderer(vendored_config.Config())

    assert renderer.environment.get_template("card.html.jinja2")
    assert renderer.environment.loader.searchpath == [str(package_root / "templates")]


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
    assert "QIQI-Bot" in html
    assert "作者 LoCCai" in html
    assert "数据驱动" in html
    assert "How To Cook" in html
    assert "渲染时间" in html
    assert "2026-08-28 23:30" in html


def test_search_card_uses_left_images_and_right_metadata() -> None:
    document = recipe_list_document(
        [
            {
                "id": "one",
                "title": "番茄炒蛋",
                "cover": {"url": "/assets/tomato.jpg", "alt": "成品"},
                "author": "LoCCai",
                "time_estimate": {"text": "15 分钟"},
                "calories": {"value": 320, "unit": "大卡"},
                "difficulty_display": "★★",
                "matched": ["title"],
            },
            {"id": "two", "title": "没有图片的菜谱"},
        ],
        {"total": 2, "page": 1, "pages": 1, "q": "番茄"},
        asset_base_url="http://cook.test",
    )
    html, _theme = CardRenderer(Config()).build_html(
        document,
        theme="light",
        now=datetime(2026, 8, 28, 15, 30, tzinfo=timezone.utc),
    )

    assert html.count('class="recipe-item"') == 2
    assert 'class="recipe-thumb"' in html
    assert 'class="recipe-copy"' in html
    assert "/assets/tomato.jpg" in html
    assert "番茄炒蛋" in html
    assert "LoCCai" in html
    assert "15 分钟" in html
    assert "320 大卡" in html
    assert "★★" in html
    assert "发送下方序号即可查看完整菜谱" in html


def test_png_dimensions() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 920, 15001)
    assert png_dimensions(png) == (920, 15001)
    assert png_dimensions(b"not png") is None
