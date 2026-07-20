"""PATCH edit-timeline 回写镜内 Shot 结构。"""

from __future__ import annotations

from core.edit.shot_flatten import compile_timeline_from_shots
from core.edit.timeline_service import patch_timeline
from core.models.entities import Project, Script, VideoPlan
from core.store.memory import MemoryStore
from tests.support.shot_fixtures import make_shot


def test_patch_timeline_syncs_shots_after_user_trim() -> None:
    """用户 PATCH 延长首镜 clip 后，VideoPlan 镜时长应经 apply_timeline_edits_to_shots 更新。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)

    shots = [
        make_shot(order=0, duration_ms=3000, text="镜一"),
        make_shot(order=1, duration_ms=3000, text="镜二"),
    ]
    plan = VideoPlan(script_id=script.id, shots=shots)
    store.set_video_plan(plan)

    timeline = compile_timeline_from_shots(shots, script_id=script.id, plan_id=plan.id)
    store.set_edit_timeline(timeline)

    layer = timeline.video_layers[0]
    first = layer.clips[0]
    extended = first.model_copy(update={"end_ms": int(first.end_ms or 0) + 800})
    patched_layers = [
        layer.model_copy(update={"clips": [extended, *layer.clips[1:]]}),
        *timeline.video_layers[1:],
    ]
    body = {
        "video_layers": [ly.model_dump() for ly in patched_layers],
        "tracks": {
            "audio": [c.model_dump() for c in timeline.tracks["audio"]],
            "subtitle": [c.model_dump() for c in timeline.tracks["subtitle"]],
        },
        "duration_ms": timeline.duration_ms + 800,
    }

    patch_timeline(
        store,
        script_id=script.id,
        project_id=project.id,
        body=body,
        expected_revision=timeline.revision,
    )

    updated = store.get_video_plan_for_script(script.id)
    assert updated is not None
    assert updated.shots[0].duration_ms >= 3800
