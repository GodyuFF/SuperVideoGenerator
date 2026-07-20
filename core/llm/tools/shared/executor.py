"""子 Agent 工具执行器：只读查询与列表类工具。"""

from core.llm.agent.react_core import AgentRunContext
from core.llm.tools.script.list import format_text_assets_list
from core.llm.tools.shared.media_list import (
    build_media_list_payload,
    format_media_list_summary,
)
from core.models.entities import MediaAssetType
from core.store.memory import MemoryStore


class AgentToolExecutor:
    """执行 Agent 只读工具（写操作仍由 llm_action.apply_action_result 处理）。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def execute_by_action(self, agent_name: str, action: str, ctx: AgentRunContext) -> str:
        """按运行时 action 名执行只读工具。"""
        script_id = ctx.script_id
        project_id = str(ctx.work_context.get("project_id", ""))

        if action == "list_text_assets":
            return self._list_text_assets(script_id)
        if action == "list_images":
            return self._list_media(project_id, script_id, MediaAssetType.IMAGE)
        if action == "get_plan":
            return self._get_video_plan(script_id)
        if action == "list_videos":
            return self._list_media(project_id, script_id, MediaAssetType.VIDEO)
        if action == "list_audio":
            return self._list_media(project_id, script_id, MediaAssetType.AUDIO)
        if action == "list_final":
            return self._list_media(project_id, script_id, MediaAssetType.FINAL)

        raise ValueError(f"Agent {agent_name} 不支持只读 action「{action}」")

    def _list_text_assets(self, script_id: str) -> str:
        return format_text_assets_list(self._store, script_id)

    def _list_media(
        self, project_id: str, script_id: str, media_type: MediaAssetType
    ) -> str:
        payload = build_media_list_payload(self._store, script_id, media_type)
        return format_media_list_summary(payload)

    def _get_video_plan(self, script_id: str) -> str:
        vp = self._store.get_video_plan_for_script(script_id)
        if not vp:
            return "当前无视频计划稿。"
        lines = [f"计划稿 {vp.id}，模式 {vp.mode.value}，共 {len(vp.shots)} 镜："]
        for shot in sorted(vp.shots, key=lambda s: s.order):
            narr = "".join(
                c.text for t in shot.audio_tracks if t.kind == "voice" for c in t.clips
            )
            if not narr and shot.sub_shots:
                narr = shot.sub_shots[0].description
            preview = f"{narr[:40]}…" if len(narr) > 40 else narr
            lines.append(
                f"- 镜{shot.order + 1}: {shot.duration_ms}ms | {preview}"
            )
        return "\n".join(lines)

    @staticmethod
    def scan_summary(store: MemoryStore, script_id: str) -> str:
        """scan_text_assets 的确定性 JSON 载荷。"""
        from core.llm.tools.image.scan import format_scan_text_assets

        return format_scan_text_assets(store, script_id)

    @staticmethod
    def load_shots_summary(store: MemoryStore, script_id: str) -> int:
        vp = store.get_video_plan_for_script(script_id)
        return len(vp.shots) if vp else 0
