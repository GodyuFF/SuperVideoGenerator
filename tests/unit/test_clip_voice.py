"""配音幕 clip 音色解析单元测试。"""

import pytest

from core.models.entities import (
    AssetScope,
    Project,
    Script,
    ShotAudioClip,
    TextAsset,
    TextAssetType,
)
from core.tts.clip_voice import resolve_voice_act_voice_name
from core.tts.engine import TtsRuntimeConfig
from core.llm.tools.tts.settings import TtsSettings
from core.store.memory import MemoryStore


@pytest.fixture
def voice_store() -> MemoryStore:
    """含单角色的最小 store。"""
    store = MemoryStore()
    project = Project(title="配音测试")
    store.add_project(project)
    script = Script(project_id=project.id, title="集一")
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="主角",
        content={"tts_voice": "zh-CN-YunxiNeural-Male", "gender": "男"},
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    return store


def _first_character_id(store: MemoryStore) -> str:
    for asset in store.text_assets.values():
        if asset.type == TextAssetType.CHARACTER:
            return asset.id
    raise AssertionError("fixture 缺少角色资产")


def test_resolve_voice_act_explicit_clip_voice(voice_store: MemoryStore):
    """clip.voice 优先于角色与默认音色。"""
    settings = TtsSettings(enabled=True, provider="edge", default_voice="zh-CN-XiaoxiaoNeural-Female")
    runtime = TtsRuntimeConfig(settings=settings)
    clip = ShotAudioClip(voice="zh-CN-YunxiNeural-Male", character_ref="txt_missing")
    assert resolve_voice_act_voice_name(voice_store, clip, runtime) == "zh-CN-YunxiNeural-Male"


def test_resolve_voice_act_from_character_tts_voice(voice_store: MemoryStore):
    """关联角色且已配置 tts_voice 时使用角色音色。"""
    char_id = _first_character_id(voice_store)
    settings = TtsSettings(enabled=True, provider="edge", default_voice="zh-CN-XiaoxiaoNeural-Female")
    runtime = TtsRuntimeConfig(settings=settings)
    clip = ShotAudioClip(character_ref=char_id)
    assert resolve_voice_act_voice_name(voice_store, clip, runtime) == "zh-CN-YunxiNeural-Male"


def test_resolve_voice_act_narrator_default(voice_store: MemoryStore):
    """无角色、无 clip.voice 时使用项目默认旁白音色。"""
    settings = TtsSettings(enabled=True, provider="edge", default_voice="zh-CN-XiaoxiaoNeural-Female")
    runtime = TtsRuntimeConfig(settings=settings)
    clip = ShotAudioClip()
    assert resolve_voice_act_voice_name(voice_store, clip, runtime) == runtime.voice_name
