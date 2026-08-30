import importlib
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from nonebot_plugin_how_to_cook.config import Config
from nonebot_plugin_how_to_cook.content import (
    Document,
    Section,
    menu_document,
    recipe_list_document,
    shopping_list_document,
    stats_document,
    week_plan_document,
)
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
    assert "发送下方序号即可查看完整内容" in html


def test_png_dimensions() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 920, 15001)
    assert png_dimensions(png) == (920, 15001)
    assert png_dimensions(b"not png") is None


def test_menu_and_stats_cards_have_specialized_layouts() -> None:
    renderer = CardRenderer(Config())
    now = datetime(2026, 8, 28, 3, 30, tzinfo=timezone.utc)
    menu = menu_document(
        {
            "meat": [{"id": "m", "title": "红烧肉"}],
            "vegetable": [{"id": "v", "title": "油麦菜"}],
            "soup": [{"id": "s", "title": "蛋花汤"}],
        },
        {"seed": "dinner", "unfilled": []},
        asset_base_url="http://cook.test",
    )
    menu_html, _ = renderer.build_html(menu, theme="light", now=now)
    assert 'class="menu-groups"' in menu_html
    assert menu_html.count('class="recipe-item"') == 3
    assert "荤菜与水产" in menu_html
    assert "六类餐食已经按需搭好" in menu_html

    stats = stats_document(
        {
            "recipes": 3,
            "tips": 1,
            "categories": [{"title": "荤菜", "count": 3}],
            "difficulty": {"1": 1},
            "methods": [{"name": "炒", "count": 2}],
            "top_ingredients": [{"name": "盐", "count": 3}],
        },
        asset_base_url="http://cook.test",
    )
    stats_html, _ = renderer.build_html(stats, theme="dark", now=now)
    assert stats_html.count('class="chart-card"') == 4
    assert "分类分布" in stats_html
    assert "--bar: 100.0%" in stats_html


def test_week_plan_and_shopping_cards_have_specialized_layouts() -> None:
    renderer = CardRenderer(Config())
    now = datetime(2026, 8, 28, 3, 30, tzinfo=timezone.utc)
    plan = week_plan_document(
        {
            "days": [
                {
                    "day": 1,
                    "meat": [
                        {
                            "id": "m",
                            "title": "宫保鸡丁",
                            "cover": {"url": "/assets/m.jpg", "alt": "成品"},
                        }
                    ],
                    "vegetable": [{"id": "v", "title": "清炒时蔬"}],
                    "soup": [{"id": "s", "title": "蛋花汤"}],
                }
            ]
        },
        {"seed": "week", "days": 1, "exclude_tags": [], "repeats": False},
        asset_base_url="http://cook.test",
    )
    plan_html, _ = renderer.build_html(plan, theme="light", now=now)
    assert 'class="week-days"' in plan_html
    assert plan_html.count('class="plan-item"') == 3
    assert "发送“第1天”查看当天详情" in plan_html
    assert "/assets/m.jpg" in plan_html

    shopping = shopping_list_document(
        {
            "items": [
                {
                    "name": "鸡蛋",
                    "display_names": ["鸡蛋", "土鸡蛋"],
                    "amounts": [{"value": 4, "unit": "个"}],
                    "unspecified": [],
                    "recipes": ["炒滑蛋"],
                }
            ],
            "recipes": [{"id": "v", "title": "炒滑蛋"}],
            "not_found": [],
        },
        {"servings": 4},
        asset_base_url="http://cook.test",
    )
    shopping_html, _ = renderer.build_html(shopping, theme="dark", now=now)
    assert 'class="shopping-grid"' in shopping_html
    assert 'class="shopping-check"' in shopping_html
    assert "鸡蛋" in shopping_html
    assert "4 个" in shopping_html
    assert "土鸡蛋" in shopping_html
