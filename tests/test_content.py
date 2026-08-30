from nonebot_plugin_how_to_cook.content import (
    Document,
    Section,
    aggregate_search_document,
    content_changelog_document,
    content_check_document,
    ingredients_discovery_document,
    menu_document,
    recipe_document,
    recipe_list_document,
    shopping_list_document,
    split_text,
    stats_document,
    week_plan_document,
)


def test_recipe_document_contains_complete_structured_text() -> None:
    data = {
        "id": "abc123",
        "title": "测试红烧肉",
        "description": "软糯鲜香",
        "category": {"id": "meat", "title": "荤菜"},
        "difficulty": 3,
        "difficulty_display": "★★★",
        "time_estimate": {"text": "90 分钟", "minutes": 90},
        "calories": {"value": 1234, "unit": "大卡"},
        "methods": ["炖", "烧"],
        "author": {"name": "Chef"},
        "created_at": "2026-01-01",
        "updated_at": "2026-01-02",
        "ingredients": [{"raw": "五花肉：500g"}],
        "tools": [{"raw": "炒锅"}],
        "steps": [{"index": 1, "group": "制作", "text": "先焯水"}],
        "notes": ["注意火候"],
        "cover": {"url": "/assets/a.jpg", "alt": "成品"},
        "content": {"markdown": "# 测试红烧肉\n\n正文"},
    }
    document = recipe_document(data, asset_base_url="http://cook.test")
    assert document.title == "测试红烧肉"
    assert document.cover_url == "/assets/a.jpg"
    assert document.article_markdown.startswith("# 测试")
    text = document.full_text()
    assert "五花肉：500g" in text
    assert "先焯水" in text
    assert "Chef" in text


def test_recipe_search_builds_numbered_visual_choices() -> None:
    document = recipe_list_document(
        [
            {"id": "1", "title": "A", "cover": None},
            {
                "id": "2",
                "title": "B",
                "cover": {"url": "/assets/b.jpg"},
                "author": "Chef",
                "difficulty_display": "★★★",
                "time_estimate": {"text": "30 分钟"},
                "calories": {"value": 520, "unit": "大卡"},
                "category": {"title": "荤菜"},
                "methods": ["炒", "煮"],
                "updated_at": "2026-08-28T12:00:00Z",
                "matched": ["title", "ingredients"],
            },
        ],
        {
            "total": 2,
            "page": 1,
            "pages": 1,
            "q": "test",
            "tag": "vegetarian",
            "exclude_tags": "spicy,seafood",
        },
        asset_base_url="http://cook.test",
    )
    assert document.layout == "recipe_list"
    assert document.cover_url is None
    assert len(document.sections) == 2
    assert [choice.identifier for choice in document.recipe_choices] == ["1", "2"]
    assert document.recipe_choices[1].cover_url == "/assets/b.jpg"
    assert document.recipe_choices[1].metadata[:4] == [
        ("作者", "Chef"),
        ("耗时", "30 分钟"),
        ("热量", "520 大卡"),
        ("难度", "★★★"),
    ]
    assert document.recipe_choices[1].matched == ["标题", "原料"]
    assert "仅看：素食" in document.description
    assert "已避开：含辣、水产" in document.description


def test_document_text_and_lossless_splitting() -> None:
    document = Document("标题", description="摘要", sections=[Section("章节", "a" * 20)])
    chunks = split_text(document.full_text(), 10)
    assert chunks
    assert "".join(chunks).replace("\n", "") == document.full_text().replace("\n", "")


def test_ingredient_discovery_exposes_coverage_and_missing_items() -> None:
    document = ingredients_discovery_document(
        [
            {
                "id": "dish",
                "title": "番茄炒蛋",
                "ingredients_match": {
                    "coverage": 0.5,
                    "hit_count": 2,
                    "total": 4,
                    "missing": ["盐", "油"],
                },
            }
        ],
        {"have": ["鸡蛋", "番茄"], "mode": "loose"},
        asset_base_url="http://cook.test",
    )
    assert document.layout == "recipe_list"
    assert document.recipe_choices[0].metadata[:2] == [("覆盖", "50%"), ("已有", "2/4")]
    assert document.recipe_choices[0].note == "还缺：盐、油"


def test_menu_groups_share_global_selection_numbers() -> None:
    document = menu_document(
        {
            "meat": [{"id": "m", "title": "红烧肉"}],
            "vegetable": [{"id": "v", "title": "油麦菜"}],
            "soup": [{"id": "s", "title": "蛋花汤"}],
        },
        {
            "seed": "dinner",
            "max_difficulty": 3,
            "unfilled": [],
            "slots": {"meat": 1, "vegetable": 1, "soup": 1},
        },
        asset_base_url="http://cook.test",
    )
    assert document.layout == "menu"
    assert [group.title for group in document.choice_groups] == [
        "荤菜与水产",
        "时蔬",
        "汤与粥",
        "早餐",
        "饮品",
        "甜品",
    ]
    assert [choice.number for choice in document.recipe_choices] == [1, 2, 3]
    assert document.shopping_recipe_ids == ["m", "v", "s"]
    assert "1 道荤菜/水产 + 1 道时蔬 + 1 道汤与粥" in document.description


def test_week_plan_and_shopping_list_have_dedicated_models() -> None:
    plan = week_plan_document(
        {
            "days": [
                {
                    "day": 1,
                    "meat": [{"id": "m", "title": "宫保鸡丁", "diet_tags": ["peanut"]}],
                    "vegetable": [{"id": "v", "title": "炒青菜"}],
                    "soup": [{"id": "s", "title": "蛋花汤"}],
                    "breakfast": [{"id": "b", "title": "牛奶燕麦"}],
                    "drink": [{"id": "d", "title": "柠檬水"}],
                    "dessert": [{"id": "x", "title": "奶冻"}],
                },
                {
                    "day": 2,
                    "meat": [{"id": "m2", "title": "可乐鸡翅"}],
                    "vegetable": [],
                    "soup": [],
                    "breakfast": [],
                    "drink": [{"id": "d2", "title": "豆浆"}],
                    "dessert": [],
                },
            ],
            "shopping_list": {
                "items": [
                    {
                        "name": "鸡蛋",
                        "display_names": ["鸡蛋"],
                        "amounts": [{"value": 4, "unit": "个", "scaled": True}],
                        "unspecified": [],
                        "recipes": ["蛋花汤"],
                    }
                ],
                "recipes": [{"id": "s", "title": "蛋花汤"}],
                "not_found": [],
            },
        },
        {
            "seed": "week",
            "days": 2,
            "exclude_tags": ["seafood"],
            "repeats": False,
            "unfilled": 0,
            "slots": {
                "meat": [1, 2],
                "vegetable": [1, 1],
                "soup": [1, 0],
                "breakfast": [1, 0],
                "drink": [1, 1],
                "dessert": [1, 0],
            },
            "shopping_list": {"items": 1, "servings": 4, "scaled": True},
        },
        asset_base_url="http://cook.test",
    )
    assert plan.layout == "week_plan"
    assert [group.title for group in plan.choice_groups] == ["第 1 天", "第 2 天"]
    assert [choice.number for choice in plan.recipe_choices] == list(range(1, 9))
    assert plan.shopping_recipe_ids == ["m", "v", "s", "b", "d", "x", "m2", "d2"]
    assert "水产" in plan.description
    assert "荤菜/水产按天 1/2 道" in plan.description
    assert plan.embedded_shopping_list is not None
    assert plan.embedded_shopping_list.shopping_items[0].amount == "4 个"
    assert plan.shopping_servings == 4

    shopping = shopping_list_document(
        {
            "items": [
                {
                    "name": "鸡蛋",
                    "display_names": ["鸡蛋", "土鸡蛋"],
                    "amounts": [{"value": 4.0, "unit": "个", "scaled": True}],
                    "unspecified": [],
                    "recipes": ["炒滑蛋"],
                },
                {
                    "name": "可选配料",
                    "display_names": ["可选配料"],
                    "amounts": [],
                    "unspecified": [],
                    "recipes": ["炒滑蛋"],
                },
            ],
            "recipes": [{"id": "v", "title": "炒滑蛋"}],
            "not_found": [],
        },
        {"requested": 1, "servings": 4},
        asset_base_url="http://cook.test",
    )
    assert shopping.layout == "shopping_list"
    assert shopping.shopping_items[0].amount == "4 个"
    assert shopping.shopping_items[0].aliases == ["土鸡蛋"]
    assert len(shopping.shopping_items) == 1
    assert "4 人份" in shopping.description


def test_ingredient_cards_explain_formula_chinese_and_colon_quantities() -> None:
    document = recipe_document(
        {
            "id": "scaled",
            "title": "兼容用量",
            "ingredients": [
                {
                    "name": "鸡蛋",
                    "quantity": "6 个",
                    "quantity_original": "1.5 个",
                    "per_serving": True,
                    "quantity_note": "份数，向上取整",
                    "scaled": True,
                    "raw": "鸡蛋：1.5 个 * 份数，向上取整",
                },
                {"name": "姜", "quantity": "2 片", "raw": "姜：两片"},
                {"name": "牛奶", "quantity": "200 ml", "raw": "牛奶：200ml"},
                {"name": "盐", "quantity": "适量", "scaled": False, "raw": "盐：适量"},
            ],
            "tools": [],
            "steps": [],
        },
        asset_base_url="http://cook.test",
    )
    text = document.full_text()
    assert "鸡蛋：6 个（每份基准 1.5 个；换算说明 份数，向上取整）" in text
    assert "姜：2 片" in text
    assert "牛奶：200 ml" in text
    assert "盐：适量（按原文保留，无法自动换算）" in text


def test_changelog_builds_numbered_selectable_groups() -> None:
    document = content_changelog_document(
        {
            "added": [{"id": "new", "title": "新菜", "created_at": "2026-08-30"}],
            "updated": [
                {"id": "up", "title": "更新菜", "updated_at": "2026-08-29"},
                {"id": "hidden", "title": "未展示", "updated_at": "2026-08-28"},
            ],
        },
        {"days": 30, "added": 1, "updated": 2},
        asset_base_url="http://cook.test",
        limit=2,
    )
    assert document.layout == "changelog"
    assert [choice.identifier for choice in document.recipe_choices] == ["new", "up"]
    assert [group.title for group in document.choice_groups] == ["新增菜谱", "近期更新"]


def test_aggregate_search_can_select_recipe_or_tip() -> None:
    document = aggregate_search_document(
        {
            "recipes": {"total": 1, "items": [{"id": "r", "title": "炒饭"}]},
            "tips": {
                "total": 1,
                "items": [{"id": "t", "title": "厨房安全", "group": "advanced"}],
            },
        },
        {"q": "厨房"},
        asset_base_url="http://cook.test",
    )
    assert [choice.kind for choice in document.recipe_choices] == ["recipe", "tip"]
    assert [choice.number for choice in document.recipe_choices] == [1, 2]


def test_stats_and_content_check_have_dedicated_presentations() -> None:
    stats = stats_document(
        {
            "recipes": 10,
            "tips": 2,
            "categories": [{"title": "荤菜", "count": 6}],
            "difficulty": {"1": 1, "2": 2, "3": 3, "4": 3, "5": 1},
            "methods": [{"name": "炒", "count": 5}],
            "top_ingredients": [{"name": "盐", "count": 8}],
            "avg_calories": 520.5,
            "recipes_with_time_estimate": 8,
        },
        asset_base_url="http://cook.test",
    )
    assert stats.layout == "stats"
    assert len(stats.charts) == 4
    assert stats.charts[0].bars[0].percent == 100

    check = content_check_document(
        {
            "up_to_date": True,
            "local": "a" * 40,
            "remote": "a" * 40,
            "checked_at": "2026-08-30T00:00:00Z",
        },
        asset_base_url="http://cook.test",
    )
    assert "最新" in check.description
    assert "不向聊天用户开放内容更新" in check.full_text()
