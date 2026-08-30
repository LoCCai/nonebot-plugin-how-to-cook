from __future__ import annotations

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from .api import HowToCookAPIError, HowToCookClient
from .commands import CommandError, parse_command
from .config import ResponseMode, ThemeMode, plugin_config
from .content import Document
from .delivery import DeliveryError, DeliveryResultUnknown, MessageDelivery
from .interaction import ShoppingListSelection, send_transient_notice, wait_for_selection
from .service import execute_command, fetch_selection_document, fetch_shopping_list_document

how_to_cook = on_command(
    "做饭",
    aliases={"怎么做", "今天吃什么"},
    priority=12,
    block=True,
)


def _client() -> HowToCookClient:
    return HowToCookClient(
        plugin_config.how_to_cook_api_base_url,
        timeout=plugin_config.how_to_cook_request_timeout,
        direct_first=plugin_config.how_to_cook_direct_first,
        proxy_fallback=plugin_config.how_to_cook_proxy_fallback,
        image_download_limit=plugin_config.how_to_cook_image_download_bytes,
    )


async def _deliver_document(
    delivery: MessageDelivery,
    bot: Bot,
    event: MessageEvent,
    document: Document,
    *,
    mode: ResponseMode,
    theme: ThemeMode | None,
) -> bool:
    try:
        await delivery.deliver(
            bot,
            event,
            document,
            mode=mode,
            theme=theme,
        )
    except DeliveryError as exc:
        await how_to_cook.finish(str(exc))
    except DeliveryResultUnknown:
        logger.exception("HowToCook 群文件投递结果未知；为避免重复不自动补发")
        return False
    except Exception:
        # A transport error may happen after OneBot accepted a message. Do not
        # issue an automatic second message because that can duplicate content.
        logger.exception("HowToCook 消息投递失败或结果未知，未自动重发")
        return False
    return True


@how_to_cook.handle()
async def handle_how_to_cook(bot: Bot, event: MessageEvent, args: Message = CommandArg()) -> None:
    try:
        command = parse_command(args.extract_plain_text().strip())
        client = _client()
        document = await execute_command(client, command, plugin_config)
    except CommandError as exc:
        await how_to_cook.finish(f"参数有误：{exc}\n发送“做饭 帮助”查看完整用法。")
    except HowToCookAPIError as exc:
        await how_to_cook.finish(exc.user_message())
    except ValueError as exc:
        await how_to_cook.finish(f"配置或接口参数有误：{exc}")
    except Exception:
        logger.exception("HowToCook 请求或内容处理失败")
        await how_to_cook.finish("读取菜谱失败了，请稍后再试。")

    mode = command.mode or plugin_config.how_to_cook_response_mode
    delivery = MessageDelivery(plugin_config, client)
    delivered = await _deliver_document(
        delivery,
        bot,
        event,
        document,
        mode=mode,
        theme=command.theme,
    )
    if not delivered or len(document.recipe_choices) <= 1:
        return

    choice_count = len(document.recipe_choices)
    allow_shopping_list = bool(document.shopping_recipe_ids)
    selection_timeout = plugin_config.how_to_cook_selection_timeout_seconds
    try:
        shopping_hint = (
            "；发送“购物清单”汇总全部用料，或发送“购物清单 4”按 4 人份换算"
            if allow_shopping_list
            else ""
        )
        await send_transient_notice(
            bot,
            event,
            (
                f"请在 {selection_timeout} 秒内发送 1–{choice_count} 的序号查看详情；"
                f"菜谱会打开完整做法，技巧会打开全文{shopping_hint}；发送“取消”结束。"
            ),
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
        selected = await wait_for_selection(
            choice_count,
            timeout=selection_timeout,
            allow_shopping_list=allow_shopping_list,
        )
    except Exception:
        logger.exception("HowToCook 等待菜谱序号失败")
        return

    if selected is None:
        await send_transient_notice(
            bot,
            event,
            "本次菜谱选择已超时，请重新发送“做饭 <关键词>”搜索。",
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
        return
    if isinstance(selected, ShoppingListSelection):
        try:
            shopping_document = await fetch_shopping_list_document(
                client,
                document.shopping_recipe_ids,
                servings=selected.servings,
            )
        except HowToCookAPIError as exc:
            await how_to_cook.finish(exc.user_message())
        except Exception:
            logger.exception("HowToCook 汇总购物清单失败")
            await how_to_cook.finish("汇总购物清单失败了，请稍后再试。")
        await _deliver_document(
            delivery,
            bot,
            event,
            shopping_document,
            mode=mode,
            theme=command.theme,
        )
        return
    if selected < 0:
        await send_transient_notice(
            bot,
            event,
            "已取消本次菜谱选择。",
            delay=plugin_config.how_to_cook_reminder_recall_seconds,
        )
        return

    choice = document.recipe_choices[selected]
    image_mode = str(command.params.get("image_mode") or plugin_config.how_to_cook_image_mode)
    try:
        selected_document = await fetch_selection_document(
            client,
            choice,
            image_mode=image_mode,
        )
    except HowToCookAPIError as exc:
        await how_to_cook.finish(exc.user_message())
    except Exception:
        logger.exception("HowToCook 获取所选条目详情失败")
        await how_to_cook.finish("读取所选内容失败了，请稍后再试。")

    await _deliver_document(
        delivery,
        bot,
        event,
        selected_document,
        mode=mode,
        theme=command.theme,
    )
