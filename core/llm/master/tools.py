"""超级视频大师可调用的 ReAct Tools。"""

from __future__ import annotations

from typing import Any, Callable

from core.conversation.index import ConversationIndex
from core.extensions.skill_registry import get_skill, list_all_skills, resolve_skill_id
from core.llm.model.react import ReActToolInfo
from core.llm.prompt.skills.allowlist import (
    filter_skill_metas_for_agent,
    is_skill_allowed_for_agent,
)
from core.llm.prompt.skills.loader import REF_BODY_MAX_CHARS, list_skill_ref_entries, read_skill_ref_body
from core.llm.tools.shared.assets_summary import (
    build_script_assets_payload,
    format_script_assets_summary,
)
from core.llm.tools.web_fetch.tool import handle_read_webpage
from core.store.memory import MemoryStore


class MasterToolExecutor:
    """执行 tool_* 行动并返回 Observation 文本。"""

    def __init__(
        self,
        store: MemoryStore,
        conversation_index: ConversationIndex | None = None,
        *,
        on_skill_persist: Callable[[str], None] | None = None,
    ) -> None:
        """初始化主编排工具执行器。"""
        self._store = store
        self._conversation_index = conversation_index
        self._on_skill_persist = on_skill_persist

    async def execute(
        self,
        tool_action: str,
        script_id: str,
        action_input: dict[str, Any] | None = None,
        *,
        session: Any | None = None,
        conversation_id: str | None = None,
    ) -> str:
        """执行主编排 tool_*；skill 相关工具可读写 session.extra。"""
        name = tool_action.removeprefix("tool_")
        args = action_input or {}
        if name == "get_plan_summary":
            return self._get_plan_summary(script_id)
        if name == "list_assets":
            return self._list_assets(script_id)
        if name == "read_webpage":
            return self._read_webpage(args)
        if name == "list_skills":
            return self._list_skills(session)
        if name == "list_skill_refs":
            return self._list_skill_refs(session)
        if name == "read_skill_ref":
            return self._read_skill_ref(session, args)
        if name == "switch_skill":
            return self._switch_skill(session, conversation_id, args)
        raise ValueError(f"未知工具行动: {tool_action}")

    def _master_profile_and_allowlists(
        self, session: Any | None
    ) -> tuple[str, dict[str, dict[str, list[str]]] | None]:
        """解析主编排当前 Profile 与全局 Skill 白名单。"""
        from core.llm.agent.config_manager import get_agent_config_manager

        mgr = get_agent_config_manager()
        allowlists = mgr.get_data().skill_allowlists_by_profile
        profile_id = ""
        if session is not None and hasattr(session, "_profile_id"):
            profile_id = str(session._profile_id() or "").strip()
        if not profile_id:
            profile_id = "default"
        return profile_id, allowlists

    def _read_webpage(self, action_input: dict[str, Any]) -> str:
        """读取网页正文。"""
        from core.llm.agent.react_core import AgentRunContext

        ctx = AgentRunContext(
            task_brief="",
            work_context={},
            script_id="",
            step_id="",
            agent_name="super_video_master",
        )
        args = dict(action_input)
        if not str(args.get("observation", "")).strip():
            args["observation"] = "读取网页"
        result = handle_read_webpage(self._store, ctx, args)
        return result.observation

    def _get_plan_summary(self, script_id: str) -> str:
        """返回计划摘要文本。"""
        plan = self._store.get_plan(script_id)
        if not plan:
            return "当前尚无计划文档。"
        lines = [f"计划版本 v{plan.version}，目标：{plan.goal}。"]
        if not plan.steps:
            lines.append("步骤列表为空。")
        else:
            for s in plan.steps:
                lines.append(f"- {s.title}（{s.type}）: {s.status.value}")
        return "\n".join(lines)

    def _list_assets(self, script_id: str) -> str:
        """返回资产清单摘要。"""
        try:
            payload = build_script_assets_payload(self._store, script_id)
        except ValueError as exc:
            return str(exc)
        return format_script_assets_summary(payload)

    def _list_skills(self, session: Any | None = None) -> str:
        """列出当前 Profile 下主编排可用的 Skill 元数据（L1）。"""
        profile_id, allowlists = self._master_profile_and_allowlists(session)
        metas = filter_skill_metas_for_agent(
            list_all_skills(),
            profile_id=profile_id,
            agent_name="super_video_master",
            skill_allowlists_by_profile=allowlists,
        )
        if not metas:
            return "当前无可用 Skill（请检查 Agent 配置中的 Skill 白名单）。"
        lines = [f"可用 Skill（{len(metas)}）："]
        for m in metas:
            aliases = f"；别名: {', '.join(m.aliases)}" if m.aliases else ""
            desc = m.description or "（无描述）"
            lines.append(f"- /{m.id} — {m.title}：{desc}{aliases}")
        lines.append(
            "建议用 ask_user_question 确认后调用 tool_switch_skill(skill_id=…) 激活。"
        )
        return "\n".join(lines)

    def _active_skill_id(self, session: Any | None) -> str:
        """从 session.extra.skill_overlay 取当前 Skill id。"""
        if session is None:
            return ""
        overlay = (session.extra or {}).get("skill_overlay") or {}
        return str(overlay.get("id") or "").strip().lower()

    def _list_skill_refs(self, session: Any | None) -> str:
        """列出当前激活 Skill 的 references 索引。"""
        skill_id = self._active_skill_id(session)
        if not skill_id:
            return "当前未激活 Skill。请先 tool_list_skills，再 tool_switch_skill。"
        entries = list_skill_ref_entries(skill_id)
        lines = [f"Skill「{skill_id}」可查阅参考（{len(entries)}）："]
        for e in entries:
            agent_hint = f"（agents: {', '.join(e.agents)}）" if e.agents else ""
            lines.append(
                f"- {e.id}：{e.title} — {e.summary or '（无摘要）'}{agent_hint}"
            )
        if not entries:
            lines.append("（无 references）")
        else:
            lines.append("正文：tool_read_skill_ref(ref_id=…)。")
        return "\n".join(lines)

    def _read_skill_ref(self, session: Any | None, args: dict[str, Any]) -> str:
        """按需读取当前 Skill 的 reference 正文。"""
        skill_id = self._active_skill_id(session)
        if not skill_id:
            return "当前未激活 Skill，无法读取 reference。"
        ref_id = str(args.get("ref_id", "")).strip()
        if not ref_id:
            return "缺少 ref_id。"
        max_chars = args.get("max_chars")
        try:
            max_chars = int(max_chars) if max_chars is not None else REF_BODY_MAX_CHARS
        except (TypeError, ValueError):
            max_chars = REF_BODY_MAX_CHARS
        result = read_skill_ref_body(skill_id, ref_id, max_chars=max_chars)
        if not result.get("ok"):
            return str(result.get("error") or "读取失败")
        title = result.get("title") or ref_id
        lines = [f"已读取 Skill「{skill_id}」参考「{title}」（id={ref_id}）"]
        if result.get("truncated"):
            lines.append(f"（正文已截断，原文约 {result.get('content_length', 0)} 字）")
        lines.append("")
        lines.append(str(result.get("content") or ""))
        return "\n".join(lines)

    def _switch_skill(
        self,
        session: Any | None,
        conversation_id: str | None,
        args: dict[str, Any],
    ) -> str:
        """激活、切换或清除当前对话 Skill，并刷新 session.extra.skill_overlay。"""
        if session is None:
            return "内部错误：缺少 ReAct session，无法切换 Skill。"
        raw = args.get("skill_id")
        if raw is None:
            raw = args.get("skillId")
        token = str(raw if raw is not None else "").strip()
        if not token:
            session.extra["skill_overlay"] = None
            if conversation_id and self._conversation_index:
                self._conversation_index.set_active_skill(conversation_id, None)
                if self._on_skill_persist:
                    self._on_skill_persist(conversation_id)
            return "已清除当前 Skill。"
        resolved = resolve_skill_id(token) or token.strip().lower()
        bundle = get_skill(resolved)
        if bundle is None:
            return f"未知 Skill「{token}」，请先 tool_list_skills 查看可用列表。"
        profile_id, allowlists = self._master_profile_and_allowlists(session)
        if not is_skill_allowed_for_agent(
            bundle.meta.id,
            profile_id=profile_id,
            agent_name="super_video_master",
            skill_allowlists_by_profile=allowlists,
        ):
            return (
                f"Skill「{bundle.meta.id}」未对本主编排开放，"
                "请在 Agent 配置页勾选该 Skill 后再试。"
            )
        overlay = bundle.to_overlay_dict()
        session.extra["skill_overlay"] = overlay
        if conversation_id and self._conversation_index:
            self._conversation_index.set_active_skill(conversation_id, bundle.meta.id)
            if self._on_skill_persist:
                self._on_skill_persist(conversation_id)
        ref_n = len(bundle.ref_index)
        return (
            f"已激活 Skill「{bundle.meta.title}」（id={bundle.meta.id}），"
            f"含 {ref_n} 条可按需查阅的 references。"
            "后续委派将携带该 Skill；详文可用 tool_list_skill_refs / tool_read_skill_ref。"
        )


_MASTER_TOOL_DESCRIPTIONS: dict[str, str] = {
    "tool_get_plan_summary": "查询当前计划版本与各步骤执行状态。",
    "tool_list_assets": "查询当前剧本的文字/图片/音频/视频/成片资产清单（含 URL 与可访问性）。",
    "tool_read_webpage": "读取指定 URL 的网页正文（只读，http/https）。",
    "tool_list_skills": "列出可用 Skill（id/title/description），用于建议用户启用。",
    "tool_list_skill_refs": "列出当前激活 Skill 的 references 索引（不含正文）。",
    "tool_read_skill_ref": "按 ref_id 读取当前 Skill 的 reference 正文。",
    "tool_switch_skill": "激活或切换对话 Skill（skill_id 为空则清除）；建议先 ask_user_question 确认。",
}

MASTER_TOOL_ACTIONS: list[str] = [
    "tool_get_plan_summary",
    "tool_list_assets",
    "tool_read_webpage",
    "tool_list_skills",
    "tool_list_skill_refs",
    "tool_read_skill_ref",
    "tool_switch_skill",
]


def build_master_tools() -> list[ReActToolInfo]:
    """主编排可调用的工具列表（与 MasterToolExecutor 行动名一致）。"""
    return [
        ReActToolInfo(
            action_name=action,
            name=action.removeprefix("tool_"),
            description=_MASTER_TOOL_DESCRIPTIONS.get(action, action),
        )
        for action in MASTER_TOOL_ACTIONS
    ]
