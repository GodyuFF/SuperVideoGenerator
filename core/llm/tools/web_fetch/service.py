"""抓取网页并提取可读正文。"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from core.llm.tools.web_fetch.extractors import (
    extract_meta_description,
    extract_page_text,
    extract_title,
    looks_like_bot_challenge,
    parse_jina_reader_text,
)
from core.llm.tools.web_fetch.settings import WebFetchSettings, get_web_fetch_settings


@dataclass(frozen=True)
class WebPageContent:
    url: str
    title: str
    content: str
    truncated: bool
    content_length: int
    extraction_method: str = "full_html"


class WebFetchError(ValueError):
    """网页读取失败。"""


_INTERNAL_API_PATH_MARKERS = ("/api/projects/",)

_BLOCKED_HOST_HINT = (
    "请使用 list_text_assets / list_audio / gather_media 等内置工具读取项目数据，"
    "勿通过 read_webpage 访问本地 API。"
)


def _hostname(raw_host: str) -> str:
    host = raw_host.lower().strip()
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    return host.split(":")[0]


def _is_blocked_host(host: str) -> bool:
    name = _hostname(host)
    if not name:
        return False
    if name in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if name.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def validate_http_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        raise WebFetchError("URL 不能为空")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise WebFetchError("仅支持 http/https URL")
    if not parsed.netloc:
        raise WebFetchError(f"无效 URL：{raw}")
    host = parsed.hostname or ""
    if _is_blocked_host(host):
        raise WebFetchError(f"不支持访问 localhost 或内网地址。{_BLOCKED_HOST_HINT}")
    path = (parsed.path or "").lower()
    if any(marker in path for marker in _INTERNAL_API_PATH_MARKERS):
        raise WebFetchError(f"不支持通过 read_webpage 访问内部 API。{_BLOCKED_HOST_HINT}")
    return raw


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[: max_chars - 1] + "…", True


def _browser_headers(cfg: WebFetchSettings) -> dict[str, str]:
    """站点兼容的浏览器请求头（避免部分 CDN 对 Accept: text/html 返回反爬壳）。"""
    return {
        "User-Agent": cfg.user_agent,
        "Accept": "*/*",
        "Accept-Language": cfg.accept_language,
    }


def _decode_html(response: httpx.Response, cfg: WebFetchSettings) -> str:
    raw = response.content
    if len(raw) > cfg.max_bytes:
        raise WebFetchError(f"响应过大（>{cfg.max_bytes} 字节）")
    encoding = response.encoding or "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _domain_root(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _fetch_html(client: httpx.Client, url: str, cfg: WebFetchSettings) -> tuple[str, str]:
    response = client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise WebFetchError(f"非 HTML 内容（Content-Type: {content_type or 'unknown'}）")
    return str(response.url), _decode_html(response, cfg)


def _fetch_with_session(
    url: str,
    cfg: WebFetchSettings,
) -> tuple[str, str]:
    """带 Cookie 会话抓取；必要时预热站点根路径。"""
    headers = _browser_headers(cfg)
    with httpx.Client(
        timeout=cfg.timeout_sec,
        follow_redirects=True,
        headers=headers,
    ) as client:
        final_url, html_text = _fetch_html(client, url, cfg)
        body, _ = extract_page_text(html_text)
        needs_retry = (
            not body.strip()
            or looks_like_bot_challenge(html_text)
        )
        if needs_retry and cfg.warmup_domain:
            client.get(_domain_root(url))
            final_url, html_text = _fetch_html(client, url, cfg)
        return final_url, html_text


def _fetch_via_jina(url: str, cfg: WebFetchSettings) -> WebPageContent:
    base = cfg.jina_reader_base.rstrip("/") + "/"
    jina_url = f"{base}{url}"
    headers = {"Accept": "text/plain", "User-Agent": cfg.user_agent}
    try:
        with httpx.Client(timeout=cfg.timeout_sec + 15, follow_redirects=True) as client:
            response = client.get(jina_url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as e:
        raise WebFetchError(f"Jina Reader 回退失败：{e}") from e

    title, content, final_url = parse_jina_reader_text(response.text, fallback_url=url)
    if not content.strip():
        raise WebFetchError("Jina Reader 未返回可用正文")
    if not title:
        title = final_url
    return WebPageContent(
        url=final_url,
        title=title,
        content=content,
        truncated=False,
        content_length=len(content),
        extraction_method="jina",
    )


def fetch_webpage(
    url: str,
    *,
    max_chars: int | None = None,
    settings: WebFetchSettings | None = None,
) -> WebPageContent:
    cfg = settings or get_web_fetch_settings()
    limit = max_chars if max_chars is not None else cfg.max_chars_default
    limit = max(500, min(int(limit), 50000))
    safe_url = validate_http_url(url)

    try:
        final_url, html_text = _fetch_with_session(safe_url, cfg)
    except httpx.HTTPError as e:
        if cfg.use_jina_fallback:
            try:
                page = _fetch_via_jina(safe_url, cfg)
            except WebFetchError:
                raise WebFetchError(f"请求失败：{e}") from e
            clipped, truncated = truncate_text(page.content, limit)
            return WebPageContent(
                url=page.url,
                title=page.title,
                content=clipped,
                truncated=truncated,
                content_length=page.content_length,
                extraction_method=page.extraction_method,
            )
        raise WebFetchError(f"请求失败：{e}") from e

    title = extract_title(html_text) or safe_url
    body, method = extract_page_text(html_text)

    if not body.strip():
        if cfg.use_jina_fallback:
            try:
                page = _fetch_via_jina(safe_url, cfg)
            except WebFetchError as jina_err:
                meta = extract_meta_description(html_text)
                if meta:
                    combined = f"{title}\n\n{meta}" if title else meta
                    clipped, truncated = truncate_text(combined, limit)
                    return WebPageContent(
                        url=final_url,
                        title=title,
                        content=clipped,
                        truncated=truncated,
                        content_length=len(combined),
                        extraction_method="meta",
                    )
                raise WebFetchError(
                    "未能从页面提取正文（可能触发站点反爬）。"
                    f"Jina 回退亦失败：{jina_err}"
                ) from jina_err
            clipped, truncated = truncate_text(page.content, limit)
            return WebPageContent(
                url=page.url,
                title=page.title or title,
                content=clipped,
                truncated=truncated,
                content_length=page.content_length,
                extraction_method=page.extraction_method,
            )
        raise WebFetchError(
            "未能从页面提取正文（可能触发站点反爬）。"
            "可启用 SVG_WEB_FETCH_USE_JINA_FALLBACK=true 或手动粘贴内容。"
        )

    clipped, truncated = truncate_text(body, limit)
    return WebPageContent(
        url=final_url,
        title=title,
        content=clipped,
        truncated=truncated,
        content_length=len(body),
        extraction_method=method,
    )
