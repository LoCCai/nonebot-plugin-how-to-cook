from nonebot_plugin_how_to_cook.content import (
    Document,
    Section,
    recipe_document,
    recipe_list_document,
    split_text,
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


def test_recipe_search_selects_first_available_cover() -> None:
    document = recipe_list_document(
        [
            {"id": "1", "title": "A", "cover": None},
            {"id": "2", "title": "B", "cover": {"url": "/assets/b.jpg"}},
        ],
        {"total": 2, "page": 1, "pages": 1, "q": "test"},
        asset_base_url="http://cook.test",
    )
    assert document.cover_url == "/assets/b.jpg"
    assert len(document.sections) == 2


def test_document_text_and_lossless_splitting() -> None:
    document = Document("标题", description="摘要", sections=[Section("章节", "a" * 20)])
    chunks = split_text(document.full_text(), 10)
    assert chunks
    assert "".join(chunks).replace("\n", "") == document.full_text().replace("\n", "")
