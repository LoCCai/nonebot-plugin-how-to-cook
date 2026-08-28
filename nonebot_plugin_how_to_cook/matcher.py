from __future__ import annotations

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg

from .api import HowToCookAPIError, HowToCookClient
from .commands import CommandError, parse_command
from .config import plugin_config
from .delivery import DeliveryError, DeliveryResultUnknown, MessageDelivery
from .service import execute_command

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
    try:
        await delivery.deliver(
            bot,
            event,
            document,
            mode=mode,
            theme=command.theme,
        )
    except DeliveryError as exc:
        await how_to_cook.finish(str(exc))
    except DeliveryResultUnknown:
        logger.exception("HowToCook 群文件投递结果未知；为避免重复不自动补发")
    except Exception:
        # A transport error may happen after OneBot accepted a message. Do not
        # issue an automatic second message because that can duplicate content.
        logger.exception("HowToCook 消息投递失败或结果未知，未自动重发")
