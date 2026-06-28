"""用户消息意图分类：由 LLM 判断是否进入视频制作 ReAct 流程。"""

from dataclasses import dataclass

from core.llm.client import LLMClient
from core.logging.setup import get_logger, log_stage
from core.prompt.builder import get_intent_system_prompt

logger = get_logger("core.super_video_master.intent")

DEFAULT_DECLINE_REPLY = "抱歉，我只能处理视频生成相关的请求。请描述您的视频创意。"


@dataclass(frozen=True)
class IntentClassification:
    """LLM 意图门卫结果。"""

    in_scope: bool
    reason: str = ""
    reply: str = ""


def _parse_intent_payload(data: dict) -> IntentClassification:
    in_scope = bool(data.get("in_scope", True))
    reason = str(data.get("reason", "")).strip()
    reply = str(data.get("reply", "")).strip()
    if not in_scope and not reply:
        reply = DEFAULT_DECLINE_REPLY
    if in_scope:
        reply = ""
    return IntentClassification(in_scope=in_scope, reason=reason, reply=reply)


async def classify_user_intent(
    llm_client: LLMClient,
    user_message: str,
    *,
    project_id: str = "",
    script_id: str = "",
) -> IntentClassification:
    """
    调用 LLM 判断用户消息是否属于视频制作范围。
    解析失败或 LLM 异常时默认放行（in_scope=True），避免误拒。
    """
    text = user_message.strip()
    if not text:
        return IntentClassification(
            in_scope=False,
            reason="空消息",
            reply="请输入您的视频创意或制作需求。",
        )

    user_content = f"用户消息：{text}"
    log_ctx = {
        "project_id": project_id,
        "script_id": script_id,
        "agent_name": "super_video_master",
        "role": "intent_gate",
    }
    try:
        raw = await llm_client.complete_json(
            get_intent_system_prompt(),
            user_content,
            log_context=log_ctx,
            summary_prefix="意图门卫",
            response_format={"type": "json_object"},
        )
        result = _parse_intent_payload(raw)
        log_stage(
            logger,
            "intent",
            "LLM 意图分类完成",
            in_scope=result.in_scope,
            reason=result.reason[:120],
        )
        return result
    except Exception as e:
        log_stage(
            logger,
            "intent",
            "LLM 意图分类失败，默认放行",
            error=str(e),
        )
        return IntentClassification(in_scope=True, reason="分类失败默认放行")
