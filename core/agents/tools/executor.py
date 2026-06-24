"""子 Agent 工具执行器：只读查询与列表类工具。"""

from core.agents.react_core import AgentRunContext
from core.constants import VIDEO_GEN_COST_PER_SHOT_USD
from core.models.entities import MediaAssetType, TextAssetType
from core.store.memory import MemoryStore


class AgentToolExecutor:
    """执行 Agent 只读工具（写操作仍由 llm_action.apply_action_result 处理）。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def execute(self, agent_name: str, tool_name: str, ctx: AgentRunContext) -> str:
        script_id = ctx.script_id
        project_id = str(ctx.work_context.get("project_id", ""))

        if tool_name == "script.list_text_assets":
            return self._list_text_assets(script_id)
        if tool_name == "image.list":
            return self._list_media(project_id, script_id, MediaAssetType.IMAGE)
        if tool_name == "storyboard.get_plan":
            return self._get_video_plan(script_id)
        if tool_name == "video.list":
            return self._list_media(project_id, script_id, MediaAssetType.VIDEO)
        if tool_name == "tts.list":
            return self._list_media(project_id, script_id, MediaAssetType.AUDIO)
        if tool_name == "edit.list_final":
            return self._list_media(project_id, script_id, MediaAssetType.FINAL)

        raise ValueError(f"Agent {agent_name} 不支持工具 {tool_name}")

    def _list_text_assets(self, script_id: str) -> str:
        assets = self._store.list_assets_for_script(script_id)
        if not assets:
            return "当前无文字资产。"
        lines = [f"共 {len(assets)} 项文字资产："]
        for a in assets:
            lines.append(f"- [{a.type.value}] {a.name} ({a.id})")
        return "\n".join(lines)

    def _list_media(
        self, project_id: str, script_id: str, media_type: MediaAssetType
    ) -> str:
        items = self._store.list_media_for_script(script_id, media_type)
        if not items:
            return f"当前无 {media_type.value} 类型媒体资产。"
        lines = [f"共 {len(items)} 项 {media_type.value} 资产："]
        for m in items:
            url_part = f" url={m.url}" if m.url else ""
            lines.append(f"- {m.name} ({m.id}){url_part}")
        return "\n".join(lines)

    def _get_video_plan(self, script_id: str) -> str:
        vp = self._store.get_video_plan_for_script(script_id)
        if not vp:
            return "当前无视频计划稿。"
        lines = [f"计划稿 {vp.id}，模式 {vp.mode.value}，共 {len(vp.shots)} 镜："]
        for shot in sorted(vp.shots, key=lambda s: s.order):
            narr = shot.narration_text
            preview = f"{narr[:40]}…" if len(narr) > 40 else narr
            lines.append(
                f"- 镜{shot.order + 1}: {shot.duration_ms}ms "
                f"{shot.camera_motion} | {preview}"
            )
        return "\n".join(lines)

    @staticmethod
    def scan_summary(store: MemoryStore, script_id: str) -> str:
        """scan_text_assets 的确定性摘要。"""
        assets = store.list_assets_for_script(script_id)
        visual = [
            a
            for a in assets
            if a.type in (TextAssetType.CHARACTER, TextAssetType.SCENE)
        ]
        return f"扫描到 {len(visual)} 个待生成图片的文字资产（人物/场景）。"

    @staticmethod
    def load_shots_summary(store: MemoryStore, script_id: str) -> tuple[int, float]:
        vp = store.get_video_plan_for_script(script_id)
        shot_count = len(vp.shots) if vp else 0
        cost = VIDEO_GEN_COST_PER_SHOT_USD * max(shot_count, 1)
        return shot_count, cost
