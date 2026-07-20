"""配音幕说话人校验单元测试。"""

from core.edit.voice_speaker import (
    CHARACTER_SPEAKER_KIND,
    NARRATOR_SPEAKER_KIND,
    build_available_voice_speakers,
    is_narrator_voice_clip,
    validate_shot_voice_speakers,
    validate_shots_voice_speakers,
    voice_clip_speaker_kind,
)
from core.models.entities import (
    AssetScope,
    Project,
    Script,
    Shot,
    ShotAudioClip,
    ShotAudioTrack,
    ShotSubShot,
    TextAsset,
    TextAssetType,
)
from core.store.memory import MemoryStore


def _store_with_character() -> tuple[MemoryStore, str, str]:
    """含单角色的最小 store。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s1")
    store.add_script(script)
    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="小明",
        content={"tts_voice": "zh-CN-YunxiNeural-Male", "gender": "男"},
        source_script_id=script.id,
    )
    store.add_text_asset(char)
    return store, script.id, char.id


def test_voice_clip_speaker_kind_narrator_vs_character() -> None:
    """空 character_ref 为旁白，非空为角色对白。"""
    assert voice_clip_speaker_kind(ShotAudioClip()) == NARRATOR_SPEAKER_KIND
    assert is_narrator_voice_clip(ShotAudioClip())
    assert voice_clip_speaker_kind(ShotAudioClip(character_ref="txt_abc")) == CHARACTER_SPEAKER_KIND
    assert not is_narrator_voice_clip(ShotAudioClip(character_ref="txt_abc"))


def test_build_available_voice_speakers_includes_narrator_and_characters() -> None:
    """可选说话人列表含旁白与剧本角色。"""
    store, script_id, char_id = _store_with_character()
    speakers = build_available_voice_speakers(store, script_id, default_narrator_voice="narrator-voice")
    assert speakers[0]["kind"] == NARRATOR_SPEAKER_KIND
    assert speakers[0]["character_ref"] == ""
    char_speakers = [s for s in speakers if s["kind"] == CHARACTER_SPEAKER_KIND]
    assert len(char_speakers) == 1
    assert char_speakers[0]["character_ref"] == char_id
    assert char_speakers[0]["name"] == "小明"


def test_validate_shot_voice_speakers_rejects_unknown_character_ref() -> None:
    """无效 character_ref 应被拒绝。"""
    store, script_id, char_id = _store_with_character()
    shot = Shot(
        order=0,
        duration_ms=3000,
        sub_shots=[ShotSubShot(start_ms=0, end_ms=3000, description="画面")],
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                clips=[
                    ShotAudioClip(start_ms=0, end_ms=1500, text="旁白段", character_ref=""),
                    ShotAudioClip(
                        start_ms=1500,
                        end_ms=3000,
                        text="对白段",
                        character_ref="txt_unknown",
                    ),
                ],
            )
        ],
    )
    issues = validate_shot_voice_speakers(shot, store, script_id)
    assert any("txt_unknown" in i for i in issues)

    shot.audio_tracks[0].clips[1].character_ref = char_id
    assert validate_shot_voice_speakers(shot, store, script_id) == []


def test_validate_shots_voice_speakers_batch() -> None:
    """批量校验仅返回有问题的镜。"""
    store, script_id, _ = _store_with_character()
    good = Shot(
        id="good",
        order=0,
        duration_ms=2000,
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                clips=[ShotAudioClip(start_ms=0, end_ms=2000, text="纯旁白")],
            )
        ],
    )
    bad = Shot(
        id="bad",
        order=1,
        duration_ms=2000,
        audio_tracks=[
            ShotAudioTrack(
                kind="voice",
                clips=[
                    ShotAudioClip(start_ms=0, end_ms=2000, text="错角色", character_ref="txt_bad")
                ],
            )
        ],
    )
    result = validate_shots_voice_speakers([good, bad], store, script_id)
    assert "good" not in result
    assert "bad" in result
