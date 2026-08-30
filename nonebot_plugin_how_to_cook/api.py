from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

_RECIPE_RESOURCES = {
    "meta",
    "ingredients",
    "tools",
    "steps",
    "sections",
    "notes",
    "images",
    "markdown",
    "html",
    "raw",
    "related",
    "jsonld",
}
_TIP_RESOURCES = {"meta", "markdown", "html", "raw"}
_ROOT_GET_ENDPOINTS = {
    "health",
    "categories",
    "recipes",
    "tips",
    "menu",
    "plan/week",
    "search",
    "stats",
    "content",
    "content/check",
    "content/changelog",
    "docs",
    "openapi.json",
}
_SAFE_QUERY_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


class HowToCookAPIError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def user_message(self) -> str:
        suffix = f"（HTTP {self.status_code}）" if self.status_code else ""
        return f"HowToCook API：{self.message}{suffix}"


@dataclass(slots=True)
class APIResult:
    endpoint: str
    url: str
    data: Any
    meta: dict[str, Any] = field(default_factory=dict)
    content_type: str = "application/json"

    @property
    def is_text(self) -> bool:
        return isinstance(self.data, str)

    @property
    def is_binary(self) -> bool:
        return isinstance(self.data, bytes)


def _validate_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("how_to_cook_api_base_url 必须是有效的 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("HowToCook API URL 不应包含凭据")
    return normalized


def _safe_segments(path: str) -> bool:
    return all(unquote(piece) not in {"", ".", ".."} for piece in path.split("/"))


def normalize_endpoint(path: str) -> tuple[str, bool]:
    """Validate a generic API endpoint and return ``(path, is_asset)``."""

    value = path.strip().lstrip("/")
    if value.startswith("api/"):
        value = value[4:]
    if not value or "?" in value or "#" in value or not _safe_segments(value):
        raise ValueError("接口路径无效；查询参数请使用 key=value 单独传入")
    if value.startswith("assets/"):
        return value, True

    pieces = value.split("/")
    valid = value in _ROOT_GET_ENDPOINTS
    if pieces[0] == "recipes" and len(pieces) in {2, 3}:
        valid = len(pieces) == 2 or pieces[2] in _RECIPE_RESOURCES
    elif pieces[0] == "tips" and len(pieces) in {2, 3}:
        valid = len(pieces) == 2 or pieces[2] in _TIP_RESOURCES
    if not valid:
        raise ValueError("只允许访问 HowToCook 已知的只读 GET 接口；内容更新 POST 不对用户开放")
    return value, False


class HowToCookClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 15.0,
        direct_first: bool = True,
        proxy_fallback: bool = True,
        image_download_limit: int = 12 * 1024 * 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = _validate_base_url(base_url)
        parsed = urlsplit(self.base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.timeout = timeout
        self.direct_first = direct_first
        self.proxy_fallback = proxy_fallback
        self.image_download_limit = image_download_limit
        self.transport = transport

    def api_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def absolute_asset_url(self, reference: str) -> str:
        value = reference.strip()
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"}:
            return value
        if value.startswith("//"):
            return f"{urlsplit(self.origin).scheme}:{value}"
        return urljoin(f"{self.origin}/", value.lstrip("/"))

    def endpoint_url(self, endpoint: str, *, asset: bool = False) -> str:
        if asset:
            return self.absolute_asset_url(endpoint)
        return self.api_url(endpoint)

    def _attempts(self) -> list[bool]:
        if self.transport is not None:
            return [False]
        if not self.direct_first:
            return [True]
        return [False, True] if self.proxy_fallback else [False]

    def _client(self, trust_env: bool) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport,
            timeout=self.timeout,
            follow_redirects=True,
            trust_env=trust_env,
            headers={"User-Agent": "nonebot-plugin-how-to-cook/0.4.2"},
        )

    async def _send_response(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str = "application/json, text/plain;q=0.9, */*;q=0.5",
    ) -> httpx.Response:
        last_error: httpx.TransportError | None = None
        for trust_env in self._attempts():
            try:
                async with self._client(trust_env) as client:
                    return await client.request(
                        method,
                        url,
                        params=params,
                        headers={"Accept": accept},
                    )
            except httpx.TransportError as exc:
                last_error = exc
        assert last_error is not None
        raise HowToCookAPIError(
            "NETWORK_ERROR",
            f"无法连接 HowToCook API：{type(last_error).__name__}",
        ) from last_error

    async def _get_response(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str = "application/json, text/plain;q=0.9, */*;q=0.5",
    ) -> httpx.Response:
        return await self._send_response("GET", url, params=params, accept=accept)

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        code = f"HTTP_{response.status_code}"
        message = f"请求失败：{response.reason_phrase}"
        try:
            payload = response.json()
        except ValueError:
            pass
        else:
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                error = payload["error"]
                code = str(error.get("code") or code)
                message = str(error.get("message") or message)
        raise HowToCookAPIError(code, message, status_code=response.status_code)

    async def request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        is_asset: bool = False,
    ) -> APIResult:
        url = self.endpoint_url(endpoint, asset=is_asset)
        response = await self._get_response(url, params=params)
        self._raise_for_error(response)
        content_type = response.headers.get("content-type", "application/octet-stream").split(
            ";", 1
        )[0]
        if content_type == "application/json" or content_type.endswith("+json"):
            try:
                payload = response.json()
            except ValueError as exc:
                raise HowToCookAPIError(
                    "INVALID_RESPONSE",
                    "API 返回了无法解析的 JSON",
                    status_code=response.status_code,
                ) from exc
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                error = payload["error"]
                raise HowToCookAPIError(
                    str(error.get("code") or "API_ERROR"),
                    str(error.get("message") or "API 返回错误"),
                    status_code=response.status_code,
                )
            if isinstance(payload, dict) and "data" in payload:
                meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
                return APIResult(endpoint, str(response.url), payload["data"], meta, content_type)
            return APIResult(endpoint, str(response.url), payload, {}, content_type)
        if content_type.startswith("text/"):
            return APIResult(endpoint, str(response.url), response.text, {}, content_type)
        return APIResult(endpoint, str(response.url), response.content, {}, content_type)

    async def post(self, endpoint: str, *, params: dict[str, Any] | None = None) -> APIResult:
        """POST to one explicitly selected, non-mutating computation endpoint."""

        if endpoint != "shopping-list":
            raise ValueError("只允许调用无状态的 shopping-list POST；内容更新 POST 不开放")
        url = self.endpoint_url(endpoint)
        response = await self._send_response("POST", url, params=params)
        self._raise_for_error(response)
        content_type = response.headers.get("content-type", "application/octet-stream").split(
            ";", 1
        )[0]
        if content_type != "application/json" and not content_type.endswith("+json"):
            raise HowToCookAPIError(
                "INVALID_RESPONSE",
                "API 返回了非 JSON 购物清单",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise HowToCookAPIError(
                "INVALID_RESPONSE",
                "API 返回了无法解析的 JSON",
                status_code=response.status_code,
            ) from exc
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error = payload["error"]
            raise HowToCookAPIError(
                str(error.get("code") or "API_ERROR"),
                str(error.get("message") or "API 返回错误"),
                status_code=response.status_code,
            )
        if isinstance(payload, dict) and "data" in payload:
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            return APIResult(endpoint, str(response.url), payload["data"], meta, content_type)
        return APIResult(endpoint, str(response.url), payload, {}, content_type)

    async def health(self) -> APIResult:
        return await self.request("health")

    async def categories(self) -> APIResult:
        return await self.request("categories")

    async def recipes(self, **params: Any) -> APIResult:
        return await self.request(
            "recipes", params={k: v for k, v in params.items() if v is not None}
        )

    async def random_recipes(self, **params: Any) -> APIResult:
        return await self.request(
            "recipes/random", params={k: v for k, v in params.items() if v is not None}
        )

    async def recipes_by_ingredients(self, **params: Any) -> APIResult:
        return await self.request(
            "recipes/by-ingredients",
            params={k: v for k, v in params.items() if v is not None},
        )

    async def menu(self, **params: Any) -> APIResult:
        return await self.request("menu", params={k: v for k, v in params.items() if v is not None})

    async def week_plan(self, **params: Any) -> APIResult:
        return await self.request(
            "plan/week",
            params={k: v for k, v in params.items() if v is not None},
        )

    async def shopping_list(
        self,
        identifiers: list[str] | tuple[str, ...],
        *,
        servings: int | None = None,
    ) -> APIResult:
        if not identifiers:
            raise ValueError("购物清单至少需要一道菜")
        if len(identifiers) > 50:
            raise ValueError("购物清单一次最多合并 50 道菜")
        return await self.post(
            "shopping-list",
            params={
                key: value
                for key, value in {
                    "ids": ",".join(identifiers),
                    "servings": servings,
                }.items()
                if value is not None
            },
        )

    async def search_all(self, query: str, *, image_mode: str | None = None) -> APIResult:
        return await self.request(
            "search",
            params={
                key: value
                for key, value in {"q": query, "image_mode": image_mode}.items()
                if value is not None
            },
        )

    async def stats(self) -> APIResult:
        return await self.request("stats")

    async def content_info(self) -> APIResult:
        return await self.request("content")

    async def content_check(self) -> APIResult:
        return await self.request("content/check")

    async def content_changelog(self, *, days: int = 30) -> APIResult:
        return await self.request("content/changelog", params={"days": days})

    async def recipe(
        self,
        identifier: str,
        *,
        resource: str | None = None,
        image_mode: str | None = None,
        servings: int | None = None,
    ) -> APIResult:
        if resource is not None and resource not in _RECIPE_RESOURCES:
            raise ValueError(f"未知菜谱子资源：{resource}")
        endpoint = f"recipes/{quote(identifier, safe='')}"
        if resource:
            endpoint += f"/{resource}"
        supports_image_mode = resource in {
            None,
            "meta",
            "sections",
            "images",
            "markdown",
            "html",
            "related",
        }
        params: dict[str, Any] = {}
        if image_mode and supports_image_mode:
            params["image_mode"] = image_mode
        if servings is not None:
            if resource != "ingredients":
                raise ValueError("份数参数仅适用于菜谱原料接口")
            params["servings"] = servings
        return await self.request(endpoint, params=params or None)

    async def related_recipes(
        self,
        identifier: str,
        *,
        limit: int | None = None,
        image_mode: str | None = None,
    ) -> APIResult:
        endpoint = f"recipes/{quote(identifier, safe='')}/related"
        return await self.request(
            endpoint,
            params={
                key: value
                for key, value in {"limit": limit, "image_mode": image_mode}.items()
                if value is not None
            },
        )

    async def tips(self, **params: Any) -> APIResult:
        return await self.request("tips", params={k: v for k, v in params.items() if v is not None})

    async def tip(
        self,
        identifier: str,
        *,
        resource: str | None = None,
        image_mode: str | None = None,
    ) -> APIResult:
        if resource is not None and resource not in _TIP_RESOURCES:
            raise ValueError(f"未知技巧子资源：{resource}")
        endpoint = f"tips/{quote(identifier, safe='')}"
        if resource:
            endpoint += f"/{resource}"
        params = (
            {"image_mode": image_mode}
            if image_mode and resource in {None, "markdown", "html"}
            else None
        )
        return await self.request(endpoint, params=params)

    async def generic(self, endpoint: str, params: dict[str, Any]) -> APIResult:
        normalized, is_asset = normalize_endpoint(endpoint)
        invalid_keys = [key for key in params if not _SAFE_QUERY_KEY.fullmatch(key)]
        if invalid_keys:
            raise ValueError(f"无效查询参数：{', '.join(invalid_keys)}")
        return await self.request(normalized, params=params or None, is_asset=is_asset)

    async def fetch_image(self, reference: str) -> bytes:
        url = self.absolute_asset_url(reference)
        response = await self._get_response(url, accept="image/*")
        self._raise_for_error(response)
        content_type = response.headers.get("content-type", "").lower()
        if content_type and not content_type.startswith("image/"):
            raise HowToCookAPIError("NOT_IMAGE", "菜谱图片返回了非图片内容")
        size_header = response.headers.get("content-length")
        if size_header and size_header.isdigit() and int(size_header) > self.image_download_limit:
            raise HowToCookAPIError("IMAGE_TOO_LARGE", "菜谱图片超过下载大小限制")
        if len(response.content) > self.image_download_limit:
            raise HowToCookAPIError("IMAGE_TOO_LARGE", "菜谱图片超过下载大小限制")
        return response.content
