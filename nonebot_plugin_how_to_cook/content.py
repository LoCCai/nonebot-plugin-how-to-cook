from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html import unescape
from typing import Any

from .api import APIResult

_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_MARK_RE = re.compile(r"(?m)^(#{1,6}|>|[-*+]\s)|[`*_~]")


@dataclass(slots=True)
class Section:
    title: str
    text: str


@dataclass(slots=True)
class Document:
    title: str
    kicker: str = "HOW TO COOK"
    description: str = ""
    stats: list[tuple[str, str]] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    cover_url: str | None = None
    cover_alt: str = "成品图"
    article_markdown: str | None = None
    article_html: str | None = None
    attachment: bytes | None = None
    attachment_content_type: str | None = None
    asset_base_url: str | None = None
    footer: str = "内容来自 HowToCook 社区，仅供烹饪参考"
    filename_hint: str = "how-to-cook"

    def summary_text(self) -> str:
        lines = [f"🍳 {self.title}"]
        if self.description:
            lines.append(self.description.strip())
        if self.stats:
            lines.append(" · ".join(f"{label} {value}" for label, value in self.stats))
        return "\n".join(lines)

    def full_text(self) -> str:
        chunks = [self.summary_text()]
        for section in self.sections:
            if section.text.strip():
                chunks.append(f"【{section.title}】\n{section.text.strip()}")
        if not self.sections and self.article_markdown:
            chunks.append(_plain_markdown(self.article_markdown))
        elif not self.sections and self.article_html:
            chunks.append(_plain_html(self.article_html))
        if self.footer:
            chunks.append(self.footer)
        return "\n\n".join(chunk for chunk in chunks if chunk.strip())

    def render_markdown(self) -> str:
        if self.article_markdown:
            return self.article_markdown
        if self.article_html:
            return ""
        chunks: list[str] = []
        if self.description:
            chunks.append(self.description)
        for section in self.sections:
            chunks.append(f"## {section.title}\n\n{section.text}")
        return "\n\n".join(chunks)


def _text(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _plain_markdown(value: str) -> str:
    return _MARKDOWN_MARK_RE.sub("", value).strip()


def _plain_html(value: str) -> str:
    return unescape(_TAG_RE.sub("", value)).strip()


def _compact_description(value: Any, limit: int = 210) -> str:
    text = _plain_markdown(_text(value, ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，。；、 ") + "…"


def _author_name(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("name"), "未知")
    return _text(value, "未知")


def _cover(data: dict[str, Any]) -> tuple[str | None, str]:
    cover = data.get("cover")
    if not isinstance(cover, dict):
        images = data.get("images")
        cover = (
            images[0]
            if isinstance(images, list) and images and isinstance(images[0], dict)
            else None
        )
    if not isinstance(cover, dict):
        return None, "成品图"
    return (
        str(cover.get("url")) if cover.get("url") else None,
        _text(cover.get("alt"), "成品图"),
    )


def _recipe_stats(data: dict[str, Any]) -> list[tuple[str, str]]:
    stats: list[tuple[str, str]] = []
    category = data.get("category")
    if isinstance(category, dict) and category.get("title"):
        stats.append(("分类", str(category["title"])))
    difficulty = data.get("difficulty_display") or data.get("difficulty")
    if difficulty:
        stats.append(("难度", str(difficulty)))
    estimate = data.get("time_estimate")
    if isinstance(estimate, dict) and estimate.get("text"):
        stats.append(("耗时", str(estimate["text"])))
    calories = data.get("calories")
    if isinstance(calories, dict) and calories.get("value") is not None:
        stats.append(("热量", f"{calories['value']} {calories.get('unit', '')}".strip()))
    methods = data.get("methods")
    if isinstance(methods, list) and methods:
        stats.append(("方式", " / ".join(str(item) for item in methods[:6])))
    author = _author_name(data.get("author"))
    if author != "未知":
        stats.append(("作者", author))
    return stats


def _ingredient_lines(items: Any) -> str:
    if not isinstance(items, list):
        return "暂无结构化原料信息"
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            lines.append(f"• {_text(item)}")
            continue
        raw = item.get("raw")
        if raw:
            lines.append(f"• {raw}")
            continue
        name = _text(item.get("name"))
        quantity = _text(item.get("quantity"), "")
        note = _text(item.get("note"), "")
        optional = "（可选）" if item.get("optional") else ""
        suffix = " ".join(part for part in (quantity, note) if part)
        lines.append(f"• {name}{optional}{f'：{suffix}' if suffix else ''}")
    return "\n".join(lines) or "暂无结构化原料信息"


def _tool_lines(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "未单独列出工具"
    lines = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"• {_text(item.get('raw') or item.get('name'))}")
        else:
            lines.append(f"• {_text(item)}")
    return "\n".join(lines)


def _step_lines(items: Any) -> str:
    if isinstance(items, dict):
        items = items.get("flat") or items.get("grouped")
    if not isinstance(items, list) or not items:
        return "暂无结构化步骤"
    lines: list[str] = []
    previous_group: str | None = None
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict):
            lines.append(f"{position}. {_text(item)}")
            continue
        if "steps" in item and isinstance(item["steps"], list):
            group = _text(item.get("group") or item.get("heading"), "步骤")
            lines.append(f"\n▌{group}")
            lines.extend(
                f"{index}. {_text(step.get('text') if isinstance(step, dict) else step)}"
                for index, step in enumerate(item["steps"], 1)
            )
            continue
        group = _text(item.get("group"), "")
        if group and group != previous_group:
            lines.append(f"\n▌{group}")
            previous_group = group
        index = item.get("index") or position
        lines.append(f"{index}. {_text(item.get('text') or item.get('raw'))}")
    return "\n".join(lines).strip()


def _notes_lines(data: dict[str, Any]) -> str:
    notes = data.get("notes")
    lines: list[str] = []
    if isinstance(notes, list):
        for note in notes:
            if isinstance(note, dict):
                lines.append(f"• {_text(note.get('text') or note.get('raw'))}")
            else:
                lines.append(f"• {_text(note)}")
    feedback = data.get("feedback_note")
    if feedback:
        lines.append(f"• {feedback}")
    return "\n".join(lines)


def recipe_document(data: Any, *, asset_base_url: str) -> Document:
    if not isinstance(data, dict):
        return generic_document("菜谱详情", data, asset_base_url=asset_base_url)
    cover_url, cover_alt = _cover(data)
    title = _text(data.get("title"), "菜谱详情")
    sections = [
        Section("原料", _ingredient_lines(data.get("ingredients"))),
        Section("工具", _tool_lines(data.get("tools"))),
        Section("烹饪步骤", _step_lines(data.get("steps"))),
    ]
    notes = _notes_lines(data)
    if notes:
        sections.append(Section("附加说明", notes))
    details = [
        f"菜谱 ID：{_text(data.get('id'))}",
        f"作者：{_author_name(data.get('author'))}",
        f"编写时间：{_text(data.get('created_at'))}",
        f"更新时间：{_text(data.get('updated_at'))}",
    ]
    sections.append(Section("来源信息", "\n".join(details)))
    content = data.get("content")
    markdown = content.get("markdown") if isinstance(content, dict) else None
    return Document(
        title=title,
        kicker="HOW TO COOK · RECIPE",
        description=_compact_description(data.get("description")),
        stats=_recipe_stats(data),
        sections=sections,
        cover_url=cover_url,
        cover_alt=cover_alt,
        article_markdown=str(markdown) if markdown else None,
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{title}",
    )


def recipe_list_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    items = data if isinstance(data, list) else []
    sections: list[Section] = []
    cover_url: str | None = None
    cover_alt = "菜谱成品图"
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        item_cover, item_alt = _cover(item)
        if cover_url is None and item_cover:
            cover_url, cover_alt = item_cover, item_alt
        stats = _recipe_stats(item)
        matched = item.get("matched")
        detail = [f"ID：{_text(item.get('id'))}"]
        if stats:
            detail.append(" · ".join(f"{key} {value}" for key, value in stats))
        if isinstance(matched, list) and matched:
            detail.append(f"命中：{' / '.join(str(value) for value in matched)}")
        sections.append(
            Section(f"{index}. {_text(item.get('title'), '未命名菜谱')}", "\n".join(detail))
        )
    total = int(meta.get("total") or 0)
    page = int(meta.get("page") or 1)
    pages = int(meta.get("pages") or 1)
    query = _text(meta.get("q"), "全部菜谱")
    description = f"“{query}”共找到 {total} 道菜谱；当前第 {page}/{pages} 页。"
    if not sections:
        sections.append(Section("没有结果", "换个菜名、拼音或原料再试试。"))
    return Document(
        title="菜谱搜索结果",
        kicker="HOW TO COOK · SEARCH",
        description=description,
        stats=[("结果", str(total)), ("页码", f"{page}/{pages}")],
        sections=sections,
        cover_url=cover_url,
        cover_alt=cover_alt,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-搜索结果",
    )


def categories_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    items = data if isinstance(data, list) else []
    lines = []
    recipe_total = 0
    for item in items:
        if isinstance(item, dict):
            title = _text(item.get("title"))
            identifier = _text(item.get("id"))
            count = _text(item.get("count"), "0")
            if str(count).isdigit():
                recipe_total += int(count)
            lines.append(f"• {title}（{identifier}）：{count} 道")
    return Document(
        title="菜谱分类",
        kicker="HOW TO COOK · CATEGORIES",
        description=f"按分类浏览 {recipe_total} 道社区菜谱。",
        stats=[("分类", str(meta.get("total") or len(items)))],
        sections=[Section("全部分类", "\n".join(lines) or "暂无分类")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-分类",
    )


def health_document(data: Any, *, asset_base_url: str) -> Document:
    payload = data if isinstance(data, dict) else {}
    stats = [
        ("菜谱", str(payload.get("recipes") or 0)),
        ("技巧", str(payload.get("tips") or 0)),
        ("分类", str(payload.get("categories") or 0)),
    ]
    details = [
        f"索引状态：{_text(payload.get('status'))}",
        f"构建时间：{_text(payload.get('index_built_at'))}",
        f"Git 元数据：{'可用' if payload.get('git_metadata') else '不可用'}",
        f"默认图片模式：{_text(payload.get('image_mode_default'))}",
    ]
    return Document(
        title="HowToCook API 状态",
        kicker="HOW TO COOK · HEALTH",
        description="只读菜谱索引服务运行正常。",
        stats=stats,
        sections=[Section("服务信息", "\n".join(details))],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-API状态",
    )


def tips_list_document(data: Any, meta: dict[str, Any], *, asset_base_url: str) -> Document:
    items = data if isinstance(data, list) else []
    sections = []
    for index, item in enumerate(items, 1):
        if isinstance(item, dict):
            sections.append(
                Section(
                    f"{index}. {_text(item.get('title'), '未命名技巧')}",
                    f"ID：{_text(item.get('id'))}\n分组：{_text(item.get('group'))}\n更新：{_text(item.get('updated_at'))}",
                )
            )
    total = int(meta.get("total") or len(sections))
    return Document(
        title="烹饪技巧",
        kicker="HOW TO COOK · TIPS",
        description=f"找到 {total} 篇厨房准备、进阶知识与安全提示。",
        stats=[("文档", str(total)), ("页码", f"{meta.get('page', 1)}/{meta.get('pages', 1)}")],
        sections=sections or [Section("没有结果", "换个关键词再试试。")],
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-烹饪技巧",
    )


def tip_document(data: Any, *, asset_base_url: str) -> Document:
    if not isinstance(data, dict):
        return generic_document("烹饪技巧", data, asset_base_url=asset_base_url)
    cover_url, cover_alt = _cover(data)
    content = data.get("content")
    markdown = content.get("markdown") if isinstance(content, dict) else None
    sections = [
        Section(
            "来源信息",
            "\n".join(
                [
                    f"文档 ID：{_text(data.get('id'))}",
                    f"分组：{_text(data.get('group'))}",
                    f"作者：{_author_name(data.get('author'))}",
                    f"更新时间：{_text(data.get('updated_at'))}",
                ]
            ),
        )
    ]
    return Document(
        title=_text(data.get("title"), "烹饪技巧"),
        kicker="HOW TO COOK · KITCHEN TIPS",
        description=_compact_description(data.get("description"), 180),
        stats=[("分组", _text(data.get("group"))), ("作者", _author_name(data.get("author")))],
        sections=sections,
        cover_url=cover_url,
        cover_alt=cover_alt,
        article_markdown=str(markdown) if markdown else None,
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{_text(data.get('title'), '技巧')}",
    )


def _json_markdown(data: Any) -> str:
    return f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"


def generic_document(
    title: str,
    data: Any,
    *,
    asset_base_url: str,
    content_type: str = "application/json",
) -> Document:
    if isinstance(data, bytes):
        return Document(
            title=title,
            description=f"二进制资源，共 {len(data)} 字节。",
            sections=[Section("资源信息", f"Content-Type：{content_type}")],
            attachment=data,
            attachment_content_type=content_type,
            asset_base_url=asset_base_url,
        )
    if isinstance(data, str):
        markdown = data if content_type in {"text/markdown", "text/plain"} else None
        html = data if content_type == "text/html" else None
        if markdown is None and html is None:
            markdown = f"```text\n{data}\n```"
        return Document(
            title=title,
            kicker="HOW TO COOK · DOCUMENT",
            article_markdown=markdown,
            article_html=html,
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}",
        )
    return Document(
        title=title,
        kicker="HOW TO COOK · API",
        article_markdown=_json_markdown(data),
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{title}",
    )


def result_document(
    title: str,
    result: APIResult,
    *,
    asset_base_url: str,
) -> Document:
    return generic_document(
        title,
        result.data,
        asset_base_url=asset_base_url,
        content_type=result.content_type,
    )


def recipe_resource_document(
    resource: str,
    result: APIResult,
    *,
    asset_base_url: str,
) -> Document:
    data = result.data
    meta = result.meta
    title = _text(meta.get("title"), "菜谱")
    if resource == "meta" and isinstance(data, dict):
        cover_url, cover_alt = _cover(data)
        counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
        details = [
            f"菜谱 ID：{_text(data.get('id'))}",
            f"作者：{_author_name(data.get('author'))}",
            f"编写时间：{_text(data.get('created_at'))}",
            f"更新时间：{_text(data.get('updated_at'))}",
            (
                "内容统计："
                f"原料 {counts.get('ingredients', 0)} · 工具 {counts.get('tools', 0)} · "
                f"步骤 {counts.get('steps', 0)} · 图片 {counts.get('images', 0)}"
            ),
        ]
        return Document(
            title=_text(data.get("title"), "菜谱元信息"),
            kicker="HOW TO COOK · METADATA",
            description=_compact_description(data.get("description")),
            stats=_recipe_stats(data),
            sections=[Section("来源与统计", "\n".join(details))],
            cover_url=cover_url,
            cover_alt=cover_alt,
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}-元信息",
        )
    if resource == "ingredients":
        sections = [Section("完整原料与用量", _ingredient_lines(data))]
    elif resource == "tools":
        sections = [Section("所需工具", _tool_lines(data))]
    elif resource == "steps":
        sections = [Section("烹饪步骤", _step_lines(data))]
    elif resource == "notes" and isinstance(data, dict):
        sections = [Section("附加说明", _notes_lines(data) or "暂无附加说明")]
    elif resource == "sections" and isinstance(data, list):
        sections = []
        markdown_parts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            heading = _text(item.get("heading"), "正文")
            markdown = _text(item.get("markdown"), "")
            sections.append(Section(heading, _plain_markdown(markdown)))
            markdown_parts.append(f"## {heading}\n\n{markdown}")
        return Document(
            title=f"{title} · 原始段落",
            kicker="HOW TO COOK · SECTIONS",
            sections=sections,
            article_markdown="\n\n".join(markdown_parts),
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}-段落",
        )
    elif resource == "images" and isinstance(data, list):
        cover_url, cover_alt = _cover({"images": data})
        lines = []
        markdown_parts = []
        for index, item in enumerate(data, 1):
            if not isinstance(item, dict):
                continue
            alt = _text(item.get("alt"), f"图片 {index}")
            url = _text(item.get("url"), "")
            lines.append(f"{index}. {alt}\n   {url}")
            if url:
                markdown_parts.append(f"### {index}. {alt}\n\n![{alt}]({url})")
        return Document(
            title=f"{title} · 图片",
            kicker="HOW TO COOK · IMAGES",
            description=f"共 {len(data)} 张菜谱图片。",
            sections=[Section("图片清单", "\n".join(lines) or "暂无图片")],
            cover_url=cover_url,
            cover_alt=cover_alt,
            article_markdown="\n\n".join(markdown_parts) or None,
            asset_base_url=asset_base_url,
            filename_hint=f"HowToCook-{title}-图片",
        )
    else:
        return result_document(
            f"{title} · {resource}",
            result,
            asset_base_url=asset_base_url,
        )
    return Document(
        title=f"{title} · {sections[0].title}",
        kicker="HOW TO COOK · STRUCTURED DATA",
        stats=[("条目", str(meta.get("total") or 0)), ("菜谱 ID", _text(meta.get("id")))],
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint=f"HowToCook-{title}-{resource}",
    )


def split_text(value: str, limit: int) -> list[str]:
    """Split text on natural boundaries without losing any content."""

    text = value.strip()
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            for offset in range(0, len(line), limit):
                chunks.append(line[offset : offset + limit].rstrip())
            continue
        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def markdown_sections(sections: Iterable[Section]) -> str:
    return "\n\n".join(f"## {section.title}\n\n{section.text}" for section in sections)


def help_document(*, asset_base_url: str) -> Document:
    sections = [
        Section(
            "搜索与筛选",
            "\n".join(
                [
                    "• 做饭 搜索 红烧肉",
                    "• 做饭 hsr（支持拼音全拼/首字母）",
                    "• 做饭 搜索 土豆 --原料 牛肉 --最高难度 3 --页 1",
                    "• 做饭 分类",
                ]
            ),
        ),
        Section(
            "完整菜谱",
            "\n".join(
                [
                    "• 做饭 详情 <ID或路径>",
                    "• 做饭 原料/工具/步骤/段落/备注/图片 <ID>",
                    "• 做饭 元信息/Markdown/HTML/原文 <ID>",
                ]
            ),
        ),
        Section(
            "烹饪技巧",
            "\n".join(
                [
                    "• 做饭 技巧 [关键词] [--分组 advanced]",
                    "• 做饭 技巧详情 <ID>",
                    "• 做饭 技巧元信息/技巧MD/技巧HTML/技巧原文 <ID>",
                ]
            ),
        ),
        Section(
            "输出与高级入口",
            "\n".join(
                [
                    "• 任意命令追加 --模式 合并|单条|组合|渲染",
                    "• 渲染命令可追加 --主题 自动|白天|夜间",
                    "• 做饭 接口 recipes q=番茄 page_size=5",
                    "• 做饭 健康",
                ]
            ),
        ),
    ]
    return Document(
        title="今天吃什么？",
        kicker="HOW TO COOK · COMMAND GUIDE",
        description="搜索 368+ 道社区菜谱，查看完整原料、步骤、成品图与厨房技巧。",
        stats=[("模式", "长图 / 合并 / 单条 / 组合"), ("主题", "自动昼夜")],
        sections=sections,
        asset_base_url=asset_base_url,
        filename_hint="HowToCook-帮助",
    )
