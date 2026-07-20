"""分镜诊断脚本与看板懒同步落盘测试。"""

from core.edit.shot_detail_sync import normalize_plan_camera_motions, sync_plan_from_tts
from core.models.entities import MediaAsset, MediaAssetType
from scripts.diagnose_storyboard import run_diagnosis
from tests.support.shot_fixtures import _store_with_two_shots


def test_normalize_plan_camera_motions_writes_canonical():
    """历史运镜别名应被规范化为 canonical 值。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    plan = plan.model_copy(
        update={
            "shots": [
                shot1.model_copy(
                    update={
                        "sub_shots": [
                            shot1.sub_shots[0].model_copy(
                                update={"camera_motion": "slow_zoom_in"}
                            )
                        ]
                    }
                ),
                shot2.model_copy(
                    update={
                        "sub_shots": [
                            shot2.sub_shots[0].model_copy(
                                update={"camera_motion": "slow_pan"}
                            )
                        ]
                    }
                ),
            ]
        }
    )
    store.set_video_plan(plan)

    _, changed = normalize_plan_camera_motions(store, script_id)
    assert changed is True
    updated = store.get_video_plan_for_script(script_id)
    assert updated
    assert updated.shots[0].sub_shots[0].camera_motion == "ken_burns_in"
    assert updated.shots[1].sub_shots[0].camera_motion == "ken_burns_pan"


def test_diagnose_storyboard_reports_data_ok_after_sync():
    """TTS 同步后诊断应判定数据层正常。"""
    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )
    sync_plan_from_tts(store, script_id)

    report = run_diagnosis(store, project_id, script_id)
    assert report["shot_count"] == 2
    assert report["cumulative_timeline_ok"] is True
    assert report["data_ok"] is True
    assert report["shots"][0]["subtitle_lines_count"] >= 1
    assert report["shots"][1]["start_ms"] == report["shots"][0]["end_ms"]


def test_sync_plan_from_tts_does_not_realign_user_edited_timeline():
    """TTS 同步仅更新分镜计划稿，即使用户已手改剪辑时间轴也不自动重投影。"""
    from core.edit.timeline import compile_timeline_from_shots

    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    plan = store.get_video_plan_for_script(script_id)
    assert plan
    timeline = compile_timeline_from_shots(store, script_id=script_id, plan=plan)
    timeline = timeline.model_copy(update={"user_edited": True})
    store.set_edit_timeline(timeline)
    rev_before = timeline.revision

    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )
    result = sync_plan_from_tts(store, script_id)
    assert "timeline_realigned" not in result
    unchanged = store.get_edit_timeline_for_script(script_id)
    assert unchanged is not None
    assert unchanged.revision == rev_before
    updated = store.get_video_plan_for_script(script_id)
    assert updated
    assert updated.shots[0].duration_ms == 2500


def test_get_board_storyboard_persists_lazy_sync(monkeypatch):
    """分镜看板 API 懒同步后应调度防抖落盘。"""
    from apps.api.routes.board import get_board
    from apps.api.state import state as app_state

    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )

    scheduled: list[bool] = []

    def _fake_schedule_save(*args, **kwargs) -> None:
        scheduled.append(True)

    monkeypatch.setattr(app_state, "store", store)
    monkeypatch.setattr(
        "core.store.persist.schedule_save",
        _fake_schedule_save,
    )

    result = get_board(project_id, "storyboard", script_id=script_id)
    assert result["kind"] == "storyboard"
    assert scheduled == [True]
    items = sorted(result["items"], key=lambda i: int(i.get("order") or 0))
    assert items[0].get("subtitle_lines")
    assert items[1]["start_ms"] == items[0]["end_ms"]


def test_get_video_plan_lazy_sync_persists(monkeypatch):
    """GET video-plan 应在懒同步后调度防抖落盘。"""
    from apps.api.routes.projects import get_video_plan
    from apps.api.state import state as app_state

    store, script_id, shot1, shot2 = _store_with_two_shots()
    project_id = list(store.projects.keys())[0]
    for shot, dur, text in (
        (shot1, 2500, "镜一"),
        (shot2, 4000, "镜二"),
    ):
        store.add_media_asset(
            MediaAsset(
                project_id=project_id,
                script_id=script_id,
                type=MediaAssetType.AUDIO,
                name=text,
                url=f"https://audio.test/{shot.id}.mp3",
                metadata={
                    "shot_id": shot.id,
                    "duration_ms": dur,
                    "subtitle_cues": [{"text": text, "start_ms": 0, "end_ms": dur}],
                },
            )
        )

    scheduled: list[bool] = []

    def _fake_schedule_save(*args, **kwargs) -> None:
        scheduled.append(True)

    monkeypatch.setattr(app_state, "store", store)
    monkeypatch.setattr(
        "core.store.persist.schedule_save",
        _fake_schedule_save,
    )

    result = get_video_plan(project_id, script_id)
    assert scheduled == [True]
    assert result["shots"][0]["audio_tracks"]
    assert result.get("shot_timings")
