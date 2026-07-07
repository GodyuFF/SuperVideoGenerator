"""从 HTML 中提取标题与正文（多策略）。"""

from __future__ import annotations

import html
import json
import re

_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_TITLE_RE = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_JSON_LD_RE = re.compile(
    r'(?is)<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
)
_META_DESC_FORWARD = re.compile(
    r'(?is)<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\']'
    r'[^>]+content=["\']([^"\']+)["\']'
)
_META_DESC_REVERSE = re.compile(
    r'(?is)<meta[^>]+content=["\']([^"\']+)["\']'
    r'[^>]+(?:name|property)=["\'](?:description|og:description)["\']'
)

# 常见 CMS / 资讯站正文容器（按优先级）
_CONTENT_START_MARKERS = (
    "mod-content__markdown",
    "article-content",
    "rich_media_content",
    "post-content",
    "entry-content",
    "markdown-body",
    "article-body",
    "mod-content",
    "article__content",
    "main-content",
    "<article",
)

_CONTENT_END_MARKERS = (
    "mod-sidebar",
    "mod-comment",
    "related-article",
    "class=\"comment",
    "class='comment",
    "<footer",
    "mod-recommend",
    "</article>",
)


def extract_title(html_text: str) -> str:
    match = _TITLE_RE.search(html_text)
    if not match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()


def html_to_text(html_text: str) -> str:
    """轻量 HTML → 纯文本。"""
    cleaned = _SCRIPT_STYLE_RE.sub("", html_text)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(
        r"(?i)</(?:p|div|li|h[1-6]|tr|section|article|blockquote|pre)>", "\n", cleaned
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    text = html.unescape(cleaned)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_like_bot_challenge(html_text: str) -> bool:
    """页面是否像反爬/JS 挑战壳（几乎无可见正文）。"""
    visible = html_to_text(html_text)
    if len(visible) >= 200:
        return False
    scripts = _SCRIPT_STYLE_RE.findall(html_text)
    if not scripts:
        return len(visible) < 50
    script_chars = sum(
        len(m.group(0)) for m in re.finditer(r"(?is)<script[^>]*>.*?</script>", html_text)
    )
    return script_chars > len(html_text) * 0.45


def extract_json_ld_body(html_text: str) -> str:
    """从 JSON-LD 提取 articleBody / description。"""
    for block in _JSON_LD_RE.findall(html_text):
        raw = block.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(data):
            if not isinstance(item, dict):
                continue
            body = item.get("articleBody") or item.get("description")
            if isinstance(body, str) and body.strip():
                return html.unescape(body.strip())
    return ""


def _walk_json_ld(node: object):
    if isinstance(node, list):
        for item in node:
            yield from _walk_json_ld(item)
    elif isinstance(node, dict):
        yield node
        graph = node.get("@graph")
        if isinstance(graph, list):
            yield from _walk_json_ld(graph)


def extract_meta_description(html_text: str) -> str:
    for pattern in (_META_DESC_FORWARD, _META_DESC_REVERSE):
        for match in pattern.finditer(html_text):
            text = html.unescape(match.group(1).strip())
            if len(text) >= 20:
                return text
    return ""


def extract_content_region_html(html_text: str) -> str:
    """按常见正文容器标记截取 HTML 片段。"""
    lower = html_text.lower()
    for marker in _CONTENT_START_MARKERS:
        idx = lower.find(marker.lower())
        if idx == -1:
            continue
        start = html_text.rfind("<", 0, idx)
        if start == -1:
            start = idx
        fragment = html_text[start:]
        end = len(fragment)
        scan_from = max(len(marker), idx - start)
        for end_marker in _CONTENT_END_MARKERS:
            eidx = fragment.lower().find(end_marker.lower(), scan_from)
            if eidx != -1:
                end = min(end, eidx)
        region = fragment[:end]
        if len(region) > 100:
            return region
    return ""


def extract_page_text(html_text: str) -> tuple[str, str]:
    """
    多策略提取正文。

    Returns:
        (text, method) method ∈ region | json_ld | meta | full_html
    """
    region_html = extract_content_region_html(html_text)
    if region_html:
        text = html_to_text(region_html)
        if len(text) >= 80:
            return text, "region"

    json_body = extract_json_ld_body(html_text)
    if len(json_body) >= 80:
        return json_body, "json_ld"

    full = html_to_text(html_text)
    if len(full) >= 80:
        return full, "full_html"

    meta = extract_meta_description(html_text)
    if meta:
        title = extract_title(html_text)
        combined = f"{title}\n\n{meta}" if title else meta
        return combined, "meta"

    if region_html:
        text = html_to_text(region_html)
        if text:
            return text, "region"

    return full, "full_html"


def parse_jina_reader_text(raw: str, *, fallback_url: str) -> tuple[str, str, str]:
    """
    解析 r.jina.ai 返回的 Markdown 文本。

    Returns:
        (title, content, url)
    """
    lines = raw.replace("\r\n", "\n").split("\n")
    title = ""
    url = fallback_url
    body_lines: list[str] = []
    phase = "head"
    for line in lines:
        if phase == "head":
            if line.startswith("Title:"):
                title = line.removeprefix("Title:").strip()
                continue
            if line.startswith("URL Source:"):
                src = line.removeprefix("URL Source:").strip()
                if src:
                    url = src
                continue
            if line.strip() == "Markdown Content:":
                phase = "body"
                continue
            if line.strip() and not line.startswith("Warning:"):
                body_lines.append(line)
            continue
        body_lines.append(line)
    content = "\n".join(body_lines).strip()
    return title, content, url
