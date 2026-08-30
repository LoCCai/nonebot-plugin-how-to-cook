from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_htmlrender")
require("nonebot_plugin_waiter")

from .config import Config  # noqa: E402
from .matcher import how_to_cook as how_to_cook  # noqa: E402

__version__ = "0.4.0"

_MENU_GROUP = {
    "key": "utilities",
    "name": "查询与工具",
    "description": "天气、铁路、域名、账号、百科、菜谱和 API 查询工具。",
    "sort_order": 40,
}

__plugin_meta__ = PluginMetadata(
    name="HowToCook 菜谱",
    description="HowToCook 六槽位周计划、购物清单、忌口筛选、智能推荐与完整菜谱客户端",
    usage="做饭 周计划｜做饭 购物清单 宫保鸡丁,炒滑蛋｜做饭 <关键词>",
    type="application",
    homepage="https://github.com/LoCCai/nonebot-plugin-how-to-cook",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={
        "Author": "LoCCai",
        "License": "MIT",
        "version": __version__,
        "menu_data": [
            {
                "func": "智能推荐、周计划与购物清单",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 随机 [数量] [--忌口 海鲜,花生]`\n"
                    "- **命令**：`<命令前缀>做饭 配餐 "
                    "[--荤 1 --素 1 --汤 1 --早餐 1 --饮料 1 --甜品 1] [--人数 4]`\n"
                    "- **命令**：`<命令前缀>做饭 周计划 [天数] [--荤 1,2,1 --早餐 1,0 --人数 4]`\n"
                    "- **回复**：配餐发送 `合并详情 [人数]`；"
                    "周计划发送 `第1天 [人数]` / `全部详情 [人数]`\n"
                    "- **回复**：配餐/周计划卡片后发送 `购物清单 [人数]`\n"
                    "- **命令**：`<命令前缀>做饭 购物清单 <菜名或ID...> [--份数 4]`\n"
                    "- **命令**：`<命令前缀>做饭 食材 <原料...> [--严格] [--数量 8]`\n"
                    "- **命令**：`<命令前缀>做饭 相关 <菜谱ID或路径> [--数量 5]`"
                ),
                "trigger_condition": "群聊与私聊用户；HowToCook API 可访问",
                "brief_des": "从一餐到一周自动搭配菜谱，按忌口过滤，并生成可勾选的采购清单。",
                "detail_des": (
                    "随机、六槽位配餐与 1–14 天周计划支持固定种子和忌口标签；荤菜、素菜、"
                    "汤、早餐、饮料、甜品均可设置 0–3，道数在周计划中还可用逗号序列逐日循环。"
                    "周计划直接使用上游内嵌购物清单；配餐/周计划卡片"
                    "可直接回复“购物清单 4”，将全部菜谱按 4 人份归一汇总；配餐回复"
                    "“合并详情”，或周计划回复“第1天”，会把完整菜谱卡和对应购物清单"
                    "放进一条合并消息。独立购物清单"
                    "命令同时接受稳定 ID 与完整菜名。食材找菜仍支持覆盖率与严格齐全模式。"
                    "所有候选共用序号选择，一个候选会直接打开完整详情。饮食标签来自原料"
                    "启发式识别，不替代医学过敏判断。\n\n## 示例\n\n"
                    "- `<命令前缀>做饭 周计划 7 --荤 1,2,1 --早餐 1,0 --人数 4`\n"
                    "- 周计划卡片后回复 `第1天 4人` 或 `全部详情 4人`\n"
                    "- 周计划卡片后回复 `购物清单 4`\n"
                    "- `<命令前缀>做饭 购物清单 宫保鸡丁,炒滑蛋 --份数 4`\n"
                    "- `<命令前缀>做饭 食材 鸡蛋 西红柿 --严格`"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 随机 [数量]"},
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 配餐 [六槽位]",
                    },
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 周计划 [天数] [逐日槽位]",
                    },
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 购物清单 <菜名...>",
                    },
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 食材 <原料...>",
                    },
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "菜谱搜索与筛选",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 搜索 <菜名|拼音|原料> [筛选]`\n"
                    "- **命令**：`<命令前缀>做饭 <关键词>`\n"
                    "- **命令**：`<命令前缀>做饭 全局搜索 <关键词>`\n"
                    "- **命令**：`<命令前缀>做饭 分类`"
                ),
                "trigger_condition": "群聊与私聊用户；HowToCook API 可访问",
                "brief_des": "按标题、拼音、原料和正文模糊搜索，并支持分类、难度、排序与分页。",
                "detail_des": (
                    "搜索支持中文标题、拼音全拼、拼音首字母、原料和正文；全局搜索会"
                    "同时检索菜谱与厨房技巧。"
                    "可追加 `--分类`、`--难度`、`--最高难度`、`--原料`、`--标签`、`--忌口`、"
                    "`--排序`、`--页` 和 `--每页`。标签支持素食、辣、海鲜、花生、蛋、"
                    "乳制品与麸质。只有一个结果时直接展示完整详情；"
                    "多个结果时发送卡片中的序号即可继续，无需复制菜谱 ID。\n\n## 示例\n\n"
                    "- `<命令前缀>做饭 hsr`\n"
                    "- `<命令前缀>做饭 搜索 --标签 素食 --忌口 辣,麸质`\n"
                    "- `<命令前缀>做饭 搜索 土豆 --原料 牛肉 --最高难度 3`"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 搜索 <关键词> [筛选]",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 <关键词>"},
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 全局搜索 <关键词>",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 分类"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "完整菜谱与进阶子资源",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 详情 <ID或路径>`\n"
                    "- **命令**：`<命令前缀>做饭 原料|工具|步骤|段落|备注|图片 <ID>`\n"
                    "- **命令**：`<命令前缀>做饭 原料 <ID> [--份数 4]`\n"
                    "- **命令**：`<命令前缀>做饭 元信息|Markdown|HTML|原文|JSONLD <ID>`"
                ),
                "trigger_condition": "一般从搜索列表回复序号；进阶命令可使用稳定 ID 或仓库相对路径",
                "brief_des": "回复搜索序号查看完整菜谱，或按 ID 直达每一类结构化数据。",
                "detail_des": (
                    "详情包含分类、难度、卡路里、用时、烹饪方式、饮食标签、作者、完整原料、"
                    "工具、步骤、备注、正文与成品图。原料接口支持按 1–100 人份换算；公式型"
                    "数量标明每份基准与换算说明，中文数量词和冒号格式采用规范化数量，缩放"
                    "后保留原始用量，模糊量仍标记为原文保留。JSON-LD 提供 schema.org Recipe 数据。"
                    "日常使用无需复制 ID。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 详情 <ID或路径>"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 步骤 <ID>"},
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 原料 <ID> --份数 4",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 Markdown <ID>"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "厨房技巧文档",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 技巧 [关键词] [--分组 <group>]`\n"
                    "- **命令**：`<命令前缀>做饭 技巧详情 <ID>`\n"
                    "- **命令**：`<命令前缀>做饭 技巧元信息|技巧MD|技巧HTML|技巧原文 <ID>`"
                ),
                "trigger_condition": "群聊与私聊用户",
                "brief_des": "搜索并查看 HowToCook 的厨房准备、进阶知识与安全提示。",
                "detail_des": (
                    "覆盖 tips 列表、详情、元信息、Markdown、HTML 与原始文档接口。"
                    "长篇技巧会自动排版成长图，超过阈值时在群聊转为群文件。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 技巧 [关键词]"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 技巧详情 <ID>"},
                ],
                "pmn_group": _MENU_GROUP,
            },
            {
                "func": "统计、内容版本与输出模式",
                "trigger_method": (
                    "- **命令**：`<命令前缀>做饭 统计`\n"
                    "- **命令**：`<命令前缀>做饭 内容版本|内容检查|更新日志 [天数]`\n"
                    "- **参数**：`--模式 合并|单条|组合|渲染`\n"
                    "- **参数**：`--主题 自动|白天|夜间`\n"
                    "- **命令**：`<命令前缀>做饭 接口 <路径> [key=value ...]`\n"
                    "- **命令**：`<命令前缀>做饭 健康`"
                ),
                "trigger_condition": (
                    "通用入口仅允许 HowToCook 的只读 GET 路由；购物清单仅开放明确计算端点，"
                    "内容更新始终拒绝"
                ),
                "brief_des": "查看全库统计、内容版本与更新日志，切换输出主题，或调用受控 API。",
                "detail_des": (
                    "统计卡片展示分类、难度、烹饪方式和高频原料；内容版本与检查只读取状态，"
                    "更新日志可按最近 1–365 天浏览并用序号打开详情，不会执行内容更新。"
                    "全局支持合并消息、单消息、组合消息与 HTML 长图。"
                    "自动主题按配置时区和时间段切换昼夜样式；默认 23:00–08:00 为夜间。"
                    "通用入口覆盖 API 已知 GET 路由；仅购物清单使用无状态计算型 POST，"
                    "内容更新 POST 始终拒绝。"
                ),
                "pmn_hidden": False,
                "pmn_triggers": [
                    {
                        "type": "command",
                        "label": "命令",
                        "value": "<命令前缀>做饭 统计",
                    },
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 内容版本"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 更新日志 30"},
                    {"type": "command", "label": "命令", "value": "<命令前缀>做饭 健康"},
                ],
                "pmn_group": _MENU_GROUP,
            },
        ],
        "pmn": {
            "markdown": True,
            "sort_order": 115,
            "menu_group": _MENU_GROUP,
        },
    },
)
