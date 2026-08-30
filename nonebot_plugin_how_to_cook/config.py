from __future__ import annotations

from typing import Literal

from nonebot import get_plugin_config
from pydantic import BaseModel, Field

ResponseMode = Literal["forward", "single", "combined", "render"]
ThemeMode = Literal["auto", "light", "dark"]


class Config(BaseModel):
    """NoneBot configuration for the plugin.

    All fields are prefixed so they can safely coexist with other plugins in a
    shared ``.env`` file.
    """

    how_to_cook_api_base_url: str = "http://127.0.0.1:3000/api"
    how_to_cook_request_timeout: float = Field(default=15.0, gt=0, le=120)
    how_to_cook_direct_first: bool = True
    how_to_cook_proxy_fallback: bool = True
    how_to_cook_image_mode: Literal["relative", "server", "proxy"] = "server"
    how_to_cook_default_page_size: int = Field(default=8, ge=1, le=100)
    how_to_cook_max_page_size: int = Field(default=20, ge=1, le=100)
    how_to_cook_selection_timeout_seconds: int = Field(default=120, ge=10, le=600)
    how_to_cook_reminder_recall_seconds: int = Field(default=15, ge=3, le=120)

    how_to_cook_response_mode: ResponseMode = "render"
    how_to_cook_render_fallback_mode: Literal["forward", "single", "combined"] = "forward"
    how_to_cook_message_chunk_size: int = Field(default=3200, ge=500, le=10000)
    how_to_cook_forward_node_size: int = Field(default=1800, ge=300, le=5000)
    how_to_cook_forward_name: str = "七七 · 今天吃什么"
    how_to_cook_forward_timeout_seconds: int = Field(default=120, ge=10, le=300)
    how_to_cook_bundle_fetch_concurrency: int = Field(default=3, ge=1, le=10)

    how_to_cook_theme: ThemeMode = "auto"
    how_to_cook_timezone: str = "Asia/Shanghai"
    how_to_cook_dark_start: str = "23:00"
    how_to_cook_dark_end: str = "08:00"
    how_to_cook_render_width: int = Field(default=920, ge=480, le=1600)
    how_to_cook_render_scale: float = Field(default=1.5, ge=1.0, le=3.0)
    how_to_cook_render_wait_ms: int = Field(default=200, ge=0, le=10000)
    how_to_cook_render_timeout_seconds: float = Field(default=45.0, gt=1, le=180)

    how_to_cook_large_image_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=256 * 1024,
        le=100 * 1024 * 1024,
    )
    how_to_cook_large_image_height: int = Field(default=14000, ge=1000, le=100000)
    how_to_cook_image_download_bytes: int = Field(
        default=12 * 1024 * 1024,
        ge=256 * 1024,
        le=100 * 1024 * 1024,
    )
    how_to_cook_upload_large_group_file: bool = True


plugin_config = get_plugin_config(Config)
