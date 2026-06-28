"""主编排结束时的 LLM 用户可见摘要。"""

from core.llm.client import LLMClient
from core.llm.streaming import OnDelta
from core.models.entities import PlanDocument, Script, ScriptStatus

from core.prompt.builder import get_summary_system_prompt


async def generate_user_summary(
    llm_client: LLMClient,
    *,
    user_message: str,
    script: Script,
    plan: PlanDocument | None,
    observations: list[str],
    project_id: str,
    script_id: str,
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
    user_content = (
        f"用户消息：{user_message}\n"
        f"剧本状态：{script.status.value}\n"
        f"剧本标题：{script.title}\n"
        f"执行步骤：\n{steps_text or '无'}\n"
        f"最近观察：\n{obs_text}\n"
    )
    log_ctx = {
        "project_id": project_id,
        "script_id": script_id,
        "agent_name": "super_video_master",
        "role": "llm_summary",
    }
    try:
        summary = await llm_client.complete_text(
            get_summary_system_prompt(),
            user_content,
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
