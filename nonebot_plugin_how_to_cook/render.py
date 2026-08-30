from __future__ import annotations

import base64
import re
import struct
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup
from nonebot import logger

from .config import Config, ThemeMode
from .content import Document
from .themes import localize_time, resolve_theme

_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_VOID_TAGS = {"br", "hr", "img"}
_BLOCKED_TAGS = {"script", "style", "iframe", "object", "embed", "form"}
_SAFE_CLASS = re.compile(r"[A-Za-z0-9 _-]{1,120}\Z")
_SAFE_STYLE = re.compile(r"text-align\s*:\s*(left|right|center)\s*;?\Z", re.I)
_WAIT_FOR_IMAGES_SCRIPT = """
async (timeoutMs) => {
  const images = Array.from(document.images);
  const waitForImage = (image) => new Promise((resolve) => {
    if (image.complete) {
      resolve();
      return;
    }
    const done = () => resolve();
    image.addEventListener("load", done, { once: true });
    image.addEventListener("error", done, { once: true });
  });

  if (timeoutMs > 0 && images.some((image) => !image.complete)) {
    let timeoutId = null;
    await Promise.race([
      Promise.all(images.map(waitForImage)),
      new Promise((resolve) => {
        timeoutId = setTimeout(resolve, timeoutMs);
      }),
    ]);
    if (timeoutId !== null) clearTimeout(timeoutId);
  }

  return {
    total: images.length,
    pending: images.filter((image) => !image.complete).length,
    failed: images.filter((image) => image.complete && image.naturalWidth === 0).length,
  };
}
"""


def _safe_url(value: str) -> bool:
    lowered = value.strip().casefold()
    return lowered.startswith(("http://", "https://", "/", "./", "../", "#"))


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in _BLOCKED_TAGS:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in _ALLOWED_TAGS:
            return
        rendered: list[str] = []
        for name, raw_value in attrs:
            name = name.casefold()
            value = raw_value or ""
            if (name in {"href", "src"} and _safe_url(value)) or name in {"alt", "title"}:
                rendered.append(f'{name}="{escape(value, quote=True)}"')
            elif name == "class" and _SAFE_CLASS.fullmatch(value):
                rendered.append(f'class="{escape(value, quote=True)}"')
            elif name == "style" and _SAFE_STYLE.fullmatch(value):
                rendered.append(f'style="{escape(value, quote=True)}"')
        suffix = f" {' '.join(rendered)}" if rendered else ""
        self.output.append(f"<{tag}{suffix}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in _BLOCKED_TAGS:
            if self.blocked_depth:
                self.blocked_depth -= 1
            return
        if not self.blocked_depth and tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.output.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self.blocked_depth:
            self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.blocked_depth:
            self.output.append(f"&#{name};")


def sanitize_html_fragment(value: str) -> str:
    sanitizer = _Sanitizer()
    sanitizer.feed(value)
    sanitizer.close()
    return "".join(sanitizer.output)


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _image_data_uri(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


class CardRenderer:
    def __init__(self, config: Config) -> None:
        self.config = config
        template_root = Path(__file__).resolve().parent / "templates"
        self.environment = Environment(
            loader=FileSystemLoader(str(template_root)),
            autoescape=select_autoescape(("html", "xml")),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.markdown = MarkdownIt("commonmark", {"html": False, "linkify": False})
        self.markdown.enable(["table", "strikethrough"])

    def choose_theme(
        self,
        override: ThemeMode | None = None,
        *,
        now: datetime | None = None,
    ) -> str:
        return resolve_theme(
            override or self.config.how_to_cook_theme,
            timezone=self.config.how_to_cook_timezone,
            dark_start=self.config.how_to_cook_dark_start,
            dark_end=self.config.how_to_cook_dark_end,
            now=now,
        )

    def build_html(
        self,
        document: Document,
        *,
        theme: ThemeMode | None = None,
        now: datetime | None = None,
        cover_bytes: bytes | None = None,
    ) -> tuple[str, str]:
        selected_theme = self.choose_theme(theme, now=now)
        if document.article_html:
            body_html = sanitize_html_fragment(document.article_html)
        else:
            body_html = self.markdown.render(document.render_markdown())
        cover_src = _image_data_uri(cover_bytes) if cover_bytes else document.cover_url
        template = self.environment.get_template("card.html.jinja2")
        html = template.render(
            document=document,
            theme=selected_theme,
            body_html=Markup(body_html),
            cover_src=cover_src,
            render_width=self.config.how_to_cook_render_width,
            rendered_at=localize_time(self.config.how_to_cook_timezone, now).strftime(
                "%Y-%m-%d %H:%M"
            ),
        )
        return html, selected_theme

    async def render(
        self,
        document: Document,
        *,
        theme: ThemeMode | None = None,
        cover_bytes: bytes | None = None,
    ) -> tuple[bytes, str]:
        from nonebot_plugin_htmlrender import get_render_context

        html, selected_theme = self.build_html(
            document,
            theme=theme,
            cover_bytes=cover_bytes,
        )
        timeout_ms = self.config.how_to_cook_render_timeout_seconds * 1000
        image_wait_ms = self.config.how_to_cook_render_image_wait_seconds * 1000
        context_options: dict[str, object] = {
            "viewport": {"width": self.config.how_to_cook_render_width, "height": 10},
            "device_scale_factor": self.config.how_to_cook_render_scale,
            "color_scheme": selected_theme,
            "timezone_id": self.config.how_to_cook_timezone,
        }
        if document.asset_base_url:
            context_options["base_url"] = document.asset_base_url.rstrip("/") + "/"

        async with get_render_context(**context_options) as page:
            # ``render_html(str)`` in htmlrender 0.7 defaults to ``networkidle`` and
            # Playwright's implicit 30 s set_content timeout. A plan card can contain
            # dozens of images, so one slow connection used to discard the whole card.
            await page.set_content(
                html,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            image_state = await page.evaluate(_WAIT_FOR_IMAGES_SCRIPT, image_wait_ms)
            if isinstance(image_state, dict) and image_state.get("pending"):
                logger.warning(
                    "HowToCook 图片等待达到上限，保留已加载资源继续截图："
                    f"pending={image_state['pending']}/{image_state.get('total', '?')}"
                )
            if self.config.how_to_cook_render_wait_ms:
                await page.wait_for_timeout(self.config.how_to_cook_render_wait_ms)
            image = await page.screenshot(
                full_page=True,
                type="png",
                timeout=timeout_ms,
            )
        return image, selected_theme
