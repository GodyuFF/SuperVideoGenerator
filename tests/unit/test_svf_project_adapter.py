"""SVF ↔ OpenCut Classic 项目适配器契约测试（ticks 换算与复合键）。"""

from __future__ import annotations

TICKS_PER_SECOND = 48000


def ms_to_ticks(ms: int) -> int:
    """毫秒转 Classic ticks（与前端 svfProjectAdapter 一致）。"""
    return round((ms / 1000) * TICKS_PER_SECOND)


def ticks_to_ms(ticks: int) -> int:
    """Classic ticks 转毫秒。"""
    return round((ticks / TICKS_PER_SECOND) * 1000)


def svf_project_key(project_id: str, script_id: str) -> str:
    """SVF 复合项目键。"""
    return f"{project_id}__{script_id}"


class TestSvfProjectAdapterContract:
    """验证适配层时间换算与键格式。"""

    def test_ms_ticks_roundtrip(self) -> None:
        """3 秒片段 ticks 往返误差应在 1ms 内。"""
        ms = 3000
        assert abs(ticks_to_ms(ms_to_ticks(ms)) - ms) <= 1

    def test_project_key_format(self) -> None:
        """复合键应可唯一定位 project + script。"""
        key = svf_project_key("proj_1", "scr_2")
        assert key == "proj_1__scr_2"
        parts = key.split("__", 1)
        assert parts == ["proj_1", "scr_2"]

    def test_zero_start_clip(self) -> None:
        """零起点 clip 的 ticks 应为 0。"""
        assert ms_to_ticks(0) == 0

    def test_timeline_metadata_patch_roundtrip(self) -> None:
        """PATCH 应支持 timeline.metadata 字段（Classic 项目快照）。"""
        from core.edit.timeline_service import patch_timeline
        from core.models.entities import EditTimeline, Project, Script
        from core.store.memory import MemoryStore

        store = MemoryStore()
        project = Project(title="p")
        store.add_project(project)
        script = Script(project_id=project.id, title="s")
        store.add_script(script)
        timeline = EditTimeline(script_id=script.id, plan_id="")
        store.set_edit_timeline(timeline)
        view = patch_timeline(
            store,
            script_id=script.id,
            project_id=project.id,
            body={"metadata": {"classic_project": {"version": 22}}},
        )
        assert view.get("metadata", {}).get("classic_project", {}).get("version") == 22
