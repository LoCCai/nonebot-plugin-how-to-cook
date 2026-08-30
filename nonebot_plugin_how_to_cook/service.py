from __future__ import annotations

from .api import HowToCookClient
from .commands import CommandError, ParsedCommand
from .config import Config
from .content import (
    Document,
    RecipeListItem,
    aggregate_search_document,
    categories_document,
    content_check_document,
    content_info_document,
    health_document,
    help_document,
    ingredients_discovery_document,
    menu_document,
    random_recipes_document,
    recipe_document,
    recipe_list_document,
    recipe_resource_document,
    related_recipes_document,
    result_document,
    stats_document,
    tip_document,
    tips_list_document,
)

_RECIPE_RESOURCES = {
    "recipe_meta": ("meta", "菜谱元信息"),
    "ingredients": ("ingredients", "菜谱原料"),
    "tools": ("tools", "菜谱工具"),
    "steps": ("steps", "烹饪步骤"),
    "sections": ("sections", "菜谱原始段落"),
    "notes": ("notes", "菜谱备注"),
    "images": ("images", "菜谱图片"),
    "markdown": ("markdown", "菜谱 Markdown"),
    "html": ("html", "菜谱 HTML"),
    "raw": ("raw", "菜谱原文"),
}
_TIP_RESOURCES = {
    "tip_meta": ("meta", "技巧元信息"),
    "tip_markdown": ("markdown", "技巧 Markdown"),
    "tip_html": ("html", "技巧 HTML"),
    "tip_raw": ("raw", "技巧原文"),
}


async def fetch_recipe_document(
    client: HowToCookClient,
    identifier: str,
    *,
    image_mode: str,
) -> Document:
    result = await client.recipe(identifier, image_mode=image_mode)
    return recipe_document(result.data, asset_base_url=client.origin)


async def fetch_tip_document(
    client: HowToCookClient,
    identifier: str,
    *,
    image_mode: str,
) -> Document:
    result = await client.tip(identifier, image_mode=image_mode)
    return tip_document(result.data, asset_base_url=client.origin)


async def fetch_selection_document(
    client: HowToCookClient,
    choice: RecipeListItem,
    *,
    image_mode: str,
) -> Document:
    if choice.kind == "tip":
        return await fetch_tip_document(client, choice.identifier, image_mode=image_mode)
    return await fetch_recipe_document(client, choice.identifier, image_mode=image_mode)


async def _expand_single_choice(
    client: HowToCookClient,
    document: Document,
    *,
    image_mode: str,
) -> Document:
    if len(document.recipe_choices) != 1:
        return document
    return await fetch_selection_document(
        client,
        document.recipe_choices[0],
        image_mode=image_mode,
    )


def _check_display_limit(params: dict[str, object], key: str, config: Config) -> None:
    value = params.get(key)
    if value is not None and int(value) > config.how_to_cook_max_page_size:
        raise CommandError(f"单次最多显示 {config.how_to_cook_max_page_size} 条")


async def execute_command(
    client: HowToCookClient,
    command: ParsedCommand,
    config: Config,
) -> Document:
    asset_base = client.origin
    image_mode = str(command.params.get("image_mode") or config.how_to_cook_image_mode)

    if command.action == "help":
        return help_document(asset_base_url=asset_base)
    if command.action == "health":
        result = await client.health()
        return health_document(result.data, asset_base_url=asset_base)
    if command.action == "categories":
        result = await client.categories()
        return categories_document(result.data, result.meta, asset_base_url=asset_base)
    if command.action == "search":
        params = dict(command.params)
        page_size = int(params.get("page_size") or config.how_to_cook_default_page_size)
        if page_size > config.how_to_cook_max_page_size:
            raise CommandError(f"每页最多显示 {config.how_to_cook_max_page_size} 条")
        params.update(q=command.query, page_size=page_size, image_mode=image_mode)
        result = await client.recipes(**params)
        document = recipe_list_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "random":
        params = dict(command.params)
        _check_display_limit(params, "count", config)
        params.setdefault("count", 1)
        params.setdefault("image_mode", image_mode)
        result = await client.random_recipes(**params)
        document = random_recipes_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "menu":
        params = dict(command.params)
        params.setdefault("image_mode", image_mode)
        result = await client.menu(**params)
        document = menu_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "by_ingredients":
        params = dict(command.params)
        params.setdefault("limit", config.how_to_cook_default_page_size)
        _check_display_limit(params, "limit", config)
        params.setdefault("image_mode", image_mode)
        result = await client.recipes_by_ingredients(**params)
        document = ingredients_discovery_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "related":
        assert command.identifier is not None
        params = dict(command.params)
        params.setdefault("limit", 5)
        _check_display_limit(params, "limit", config)
        result = await client.related_recipes(
            command.identifier,
            limit=int(params["limit"]),
            image_mode=str(params.get("image_mode") or image_mode),
        )
        document = related_recipes_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "aggregate_search":
        assert command.query is not None
        result = await client.search_all(command.query, image_mode=image_mode)
        document = aggregate_search_document(
            result.data,
            result.meta,
            asset_base_url=asset_base,
        )
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "stats":
        result = await client.stats()
        return stats_document(result.data, asset_base_url=asset_base)
    if command.action == "content_info":
        result = await client.content_info()
        return content_info_document(result.data, asset_base_url=asset_base)
    if command.action == "content_check":
        result = await client.content_check()
        return content_check_document(result.data, asset_base_url=asset_base)
    if command.action == "recipe":
        assert command.identifier is not None
        return await fetch_recipe_document(client, command.identifier, image_mode=image_mode)
    if command.action in _RECIPE_RESOURCES:
        assert command.identifier is not None
        resource, title = _RECIPE_RESOURCES[command.action]
        result = await client.recipe(command.identifier, resource=resource, image_mode=image_mode)
        if resource not in {"markdown", "html", "raw"}:
            return recipe_resource_document(
                resource,
                result,
                asset_base_url=asset_base,
            )
        return result_document(title, result, asset_base_url=asset_base)
    if command.action == "tips":
        params = dict(command.params)
        page_size = int(params.get("page_size") or config.how_to_cook_default_page_size)
        if page_size > config.how_to_cook_max_page_size:
            raise CommandError(f"每页最多显示 {config.how_to_cook_max_page_size} 条")
        params.update(q=command.query, page_size=page_size)
        result = await client.tips(**params)
        document = tips_list_document(result.data, result.meta, asset_base_url=asset_base)
        return await _expand_single_choice(client, document, image_mode=image_mode)
    if command.action == "tip":
        assert command.identifier is not None
        return await fetch_tip_document(client, command.identifier, image_mode=image_mode)
    if command.action in _TIP_RESOURCES:
        assert command.identifier is not None
        resource, title = _TIP_RESOURCES[command.action]
        result = await client.tip(command.identifier, resource=resource, image_mode=image_mode)
        return result_document(title, result, asset_base_url=asset_base)
    if command.action == "api":
        assert command.identifier is not None
        result = await client.generic(command.identifier, command.params)
        return result_document(
            f"API · {command.identifier}",
            result,
            asset_base_url=asset_base,
        )
    raise CommandError(f"未实现的命令：{command.action}")
