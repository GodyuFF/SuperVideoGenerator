"""工作台图文资产 AI 草稿生成单元测试。"""

import pytest

from core.assets.user_crud import user_create_text_asset
from core.llm.tools.workbench.generate_text_asset_draft import (
    normalize_draft_payload,
    summary_fallback,
)
from core.models.entities import Project, Script, ScriptStatus, TextAssetType
from core.store.memory import MemoryStore


def test_normalize_draft_payload_character():
    """规范化 LLM 返回的角色草稿 JSON。"""
    raw = {
        "name": "林侦探",
        "content": {
            "summary": "冷峻青年侦探",
            "description": "身穿深灰风衣的青年侦探站在雨夜霓虹街头，路灯在湿漉漉的路面拉出长长倒影，远处高楼广告牌闪烁。" * 2,
            "prompt_hint": "侧光",
            "visual_style": "赛博写实",
            "color_palette": "冷蓝",
            "role": "主角",
            "gender": "男",
        },
    }
    out = normalize_draft_payload("character", raw)
    assert out["name"] == "林侦探"
    assert out["content"]["summary"]
    assert len(out["content"]["description"]) >= 80


def test_summary_fallback_uses_description():
    """缺 summary 时从 description 截取兜底。"""
    content = {"description": "雨夜街头。霓虹闪烁。"}
    assert "雨夜" in summary_fallback("备用名", content)


@pytest.fixture
def ctx():
    store = MemoryStore()
    project = Project(title="P")
    store.add_project(project)
    script = Script(project_id=project.id, title="S", status=ScriptStatus.DRAFT)
    store.add_script(script)
    return store, project.id, script.id


def test_user_create_frame(ctx):
    """手动创建剧本画面 frame 资产（精简五块）。"""
    store, pid, sid = ctx
    frame = user_create_text_asset(
        store,
        project_id=pid,
        script_id=sid,
        asset_type="frame",
        name="开场画面",
        content={
            "summary": "城市黎明",
            "image_prompt": "高空俯瞰清晨城市天际线，薄雾笼罩楼宇，暖色晨光从东侧云层渗出。" * 3,
            "notes": "开场情绪：静谧",
        },
    )
    assert frame.type == TextAssetType.FRAME
    assert frame.scope.value == "script_private"
    assert frame.content.get("image_prompt")
    assert frame.content.get("notes") == "开场情绪：静谧"
    assert frame.content.get("prompt_locked") is True


def test_normalize_draft_payload_frame():
    """画面草稿须含 image_prompt。"""
    raw = {
        "name": "蜂巢入口",
        "content": {
            "summary": "夕阳下的蜂巢",
            "image_prompt": "温暖夕阳下巨大的六角蜂巢入口，橙金色光晕，蜜蜂飞舞。" * 3,
            "notes": "节奏舒缓",
        },
    }
    out = normalize_draft_payload("frame", raw)
    assert out["content"]["image_prompt"]
    assert out["content"]["prompt_locked"] is True
