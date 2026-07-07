"""主编排结束时的 LLM 用户可见摘要。"""

from core.conversation import ConversationStore
from core.llm.client import LLMClient
from core.llm.streaming import OnDelta
from core.models.entities import PlanDocument, Script, ScriptStatus
from core.llm.prompt.builder import get_summary_system_prompt
from core.llm.prompt.chat_messages import build_llm_request_ordered, build_master_react_chat_history


async def generate_user_summary(
    llm_client: LLMClient,
    *,
    user_message: str,
    script: Script,
    plan: PlanDocument | None,
    observations: list[str],
    project_id: str,
    script_id: str,
    conversation_id: str = "",
    conversations: ConversationStore | None = None,
    on_delta: OnDelta | None = None,
) -> str:
    """调用 LLM 流式生成结束摘要；失败时返回模板兜底。"""
    steps_text = ""
    if plan and plan.steps:
        steps_text = "\n".join(
            f"- {s.title}: {s.status.value}" + (f" ({s.error})" if s.error else "")
            for s in plan.steps
        )
    obs_text = "\n".join(observations[-8:]) if observations else "无"
    turn_user = (
        f"请根据以上对话与以下执行状态，生成本轮用户可见结束摘要：\n"
        f"剧本状态：{script.status.value}\n"
        f"剧本标题：{script.title}\n"
        f"执行步骤：\n{steps_text or '无'}\n"
        f"最近观察：\n{obs_text}\n"
    )
    chat_history: list[dict[str, str]] | None = None
    if conversations and conversation_id:
        chat_history = build_master_react_chat_history(conversations, conversation_id)
    request = build_llm_request_ordered(
        system_prompt=get_summary_system_prompt(),
        history=chat_history,
        turn_user=turn_user,
    )
    log_ctx = {
        "project_id": project_id,
        "script_id": script_id,
        "conversation_id": conversation_id,
        "agent_name": "super_video_master",
        "role": "llm_summary",
    }
    try:
        summary = await llm_client.complete(
            request,
            log_context=log_ctx,
            summary_prefix="用户摘要",
            on_delta=on_delta,
        )
        summary = summary.strip()
        if summary:
            return summary
    except Exception:
        pass

    if script.status == ScriptStatus.COMPLETED:
        return "已完成视频制作流程，剧本与资产已生成，可在右侧查看具体内容。"
    if script.status == ScriptStatus.FAILED:
        return "执行未能完成，请查看右侧计划步骤中的错误信息。"
    return f"当前状态：{script.status.value}。"
