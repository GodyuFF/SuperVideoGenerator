"""read_webpage 网页读取 tool 测试。"""

from unittest.mock import MagicMock

import pytest

from core.llm.agent.react_core import AgentRunContext
from core.llm.agent.definitions import AGENT_DEFINITIONS
from core.llm.tools import get_tool_registry
from core.llm.tools.shared.agent_tools import read_actions
from core.llm.tools.web_fetch.extractors import (
    extract_page_text,
    extract_title,
    html_to_text,
    looks_like_bot_challenge,
    parse_jina_reader_text,
)
from core.llm.tools.web_fetch.service import WebFetchError, fetch_webpage, validate_http_url
from core.llm.tools.web_fetch.settings import WebFetchSettings
from core.llm.tools.web_fetch.tool import READ_WEBPAGE_TOOL_NAME, handle_read_webpage

_SAMPLE_HTML = """
<html><head><title>Example Page</title></head>
<body>
<script>ignore()</script>
<p>Hello <b>world</b>.</p>
<p>Second paragraph for testing.</p>
</body></html>
"""

_TENCENT_ARTICLE_SNIPPET = """
<html><head><title>LangChain 文章</title></head>
<body>
<div class="mod-content"><div class="mod-content__markdown">
<p>作者：腾讯团队</p>
<p>在大语言模型 LLM 快速发展的时代，LangChain 成为重要框架。</p>
<h4>1. LangChain 简介</h4>
<p>LangChain 由 Harrison Chase 创建，用于构建 LLM 应用。</p>
</div></div>
<div class="mod-sidebar">侧边栏导航</div>
</body></html>
"""

_BOT_CHALLENGE_HTML = """
<!DOCTYPE html><html><body>
<script>window.challenge=function(){return 1};/* """ + ("x" * 5000) + """ */</script>
</body></html>
"""

_JINA_SAMPLE = """Title: 示例文章

URL Source: https://example.com/a

Markdown Content:
# 标题

正文第一段内容足够长用于测试提取逻辑是否正常运作。
"""


def test_validate_http_url():
    assert validate_http_url("https://example.com/doc") == "https://example.com/doc"
    with pytest.raises(WebFetchError):
        validate_http_url("ftp://example.com")
    with pytest.raises(WebFetchError):
        validate_http_url("")


def test_html_to_text():
    text = html_to_text(_SAMPLE_HTML)
    assert "Hello world." in text
    assert "ignore()" not in text
    assert "Second paragraph" in text


def test_extract_title():
    assert extract_title(_SAMPLE_HTML) == "Example Page"


def test_extract_tencent_region():
    text, method = extract_page_text(_TENCENT_ARTICLE_SNIPPET)
    assert method == "region"
    assert "LangChain" in text
    assert "侧边栏" not in text


def test_bot_challenge_detection():
    assert looks_like_bot_challenge(_BOT_CHALLENGE_HTML)
    assert not looks_like_bot_challenge(_TENCENT_ARTICLE_SNIPPET)


def test_parse_jina_reader_text():
    title, content, url = parse_jina_reader_text(_JINA_SAMPLE, fallback_url="https://x")
    assert title == "示例文章"
    assert "正文第一段" in content
    assert url == "https://example.com/a"


def test_read_webpage_registered_for_all_agents():
    registry = get_tool_registry()
    assert registry.has(READ_WEBPAGE_TOOL_NAME)
    spec = registry.get(READ_WEBPAGE_TOOL_NAME)
    assert spec is not None
    assert spec.agent == "common"
    assert spec.read_only
    excluded = {
        "storyboard_agent",
        "tts_agent",
        "editing_agent",
        "image_agent",
        "video_agent",
    }
    allowed = set(AGENT_DEFINITIONS) - excluded
    for name in AGENT_DEFINITIONS:
        if name in excluded:
            assert READ_WEBPAGE_TOOL_NAME not in read_actions(name)
        else:
            assert READ_WEBPAGE_TOOL_NAME in read_actions(name)
    assert "script_agent" in allowed


def test_validate_http_url_rejects_localhost_and_internal_api():
    with pytest.raises(WebFetchError, match="localhost"):
        validate_http_url("http://localhost/plan/script_x/storyboard")
    with pytest.raises(WebFetchError, match="localhost"):
        validate_http_url("http://127.0.0.1/script/x")
    with pytest.raises(WebFetchError, match="内置工具"):
        validate_http_url("http://example.com/api/projects/proj_x/assets")


def test_handle_read_webpage_rejects_localhost():
    store = MagicMock()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
    )
    result = handle_read_webpage(
        store,
        ctx,
        {
            "observation": "读本地",
            "url": "http://localhost/api/projects/p1/assets",
        },
    )
    assert not result.ok
    assert "内置工具" in result.observation


def test_handle_read_webpage_success(monkeypatch):
    monkeypatch.setattr(
        "core.llm.tools.web_fetch.tool.fetch_webpage",
        lambda url, max_chars=None: MagicMock(
            url=url,
            title="Example Page",
            content="Hello world.",
            truncated=False,
            content_length=12,
            extraction_method="region",
        ),
    )
    store = MagicMock()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
    )
    result = handle_read_webpage(
        store,
        ctx,
        {"observation": "读取参考页", "url": "https://example.com"},
    )
    assert result.ok
    assert result.structured["valid"] is True
    assert "Hello world." in result.observation


def test_handle_read_webpage_missing_url():
    store = MagicMock()
    ctx = AgentRunContext(
        task_brief="",
        work_context={},
        script_id="s1",
        step_id="step1",
        agent_name="script_agent",
    )
    result = handle_read_webpage(store, ctx, {"observation": "读网页", "url": "   "})
    assert not result.ok


def test_fetch_webpage_http(monkeypatch):
    class FakeResponse:
        url = "https://example.com/page"
        encoding = "utf-8"
        content = _SAMPLE_HTML.encode("utf-8")
        headers = {"content-type": "text/html; charset=utf-8"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(
        "core.llm.tools.web_fetch.service.httpx.Client",
        FakeClient,
    )
    page = fetch_webpage(
        "https://example.com/page",
        settings=WebFetchSettings(use_jina_fallback=False, warmup_domain=False),
    )
    assert page.title == "Example Page"
    assert "Hello world." in page.content


def test_fetch_webpage_jina_fallback(monkeypatch):
    bot_html = _BOT_CHALLENGE_HTML

    class BotResponse:
        def __init__(self):
            self.url = "https://cloud.tencent.com/developer/article/1"
            self.encoding = "utf-8"
            self.content = bot_html.encode()
            self.headers = {"content-type": "text/html; charset=utf-8"}

        def raise_for_status(self):
            return None

    class SessionClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return BotResponse()

    class JinaClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            text = _JINA_SAMPLE
            return MagicMock(
                text=text,
                raise_for_status=lambda: None,
            )

    clients = [SessionClient, JinaClient]

    def client_factory(*args, **kwargs):
        return clients.pop(0)(*args, **kwargs)

    monkeypatch.setattr(
        "core.llm.tools.web_fetch.service.httpx.Client",
        client_factory,
    )
    page = fetch_webpage(
        "https://cloud.tencent.com/developer/article/1",
        settings=WebFetchSettings(warmup_domain=False, use_jina_fallback=True),
    )
    assert page.extraction_method == "jina"
    assert "正文第一段" in page.content
