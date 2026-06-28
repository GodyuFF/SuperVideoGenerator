"""测试用脚本化 LLM 客户端：不发起真实 HTTP，按流水线返回确定性响应。"""

import json
import re
from typing import Any

from core.agents.react_core import AgentRunContext
from core.constants import VIDEO_GEN_COST_PER_SHOT_USD
from core.llm.xml_protocol import format_react_xml
from core.models.entities import VideoStyleMode
from core.super_video_master.actions import ACTION_TO_STEP, pipeline_for_style, STEP_META


class ScriptedLLMClient:
    """模拟 LLMClient.complete_xml_react / complete_json，供单元测试使用。"""

    def __init__(self, style_mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE) -> None:
        self._style_mode = style_mode
        self._master_completed: set[str] = set()
        self._agent_state: dict[str, set[str]] = {}

    async def complete_xml_react(
        self,
        role_description: str,
        context_xml: str,
        log_context: dict[str, Any] | None = None,
        on_delta: Any = None,
    ) -> str:
        ctx = log_context or {}
        role = ctx.get("role", "")
        if role == "master":
            result = self._master_react(context_xml)
        elif role == "sub_agent":
            result = self._sub_agent_react(ctx, context_xml)
        else:
            result = format_react_xml("默认结束", "finish")

        if on_delta:
            from core.llm.streaming import ReactXmlThoughtParser

            parser = ReactXmlThoughtParser()
            for char in result:
                thought_delta = parser.feed(char)
                if thought_delta:
                    await on_delta(thought_delta)
        return result

    def _master_react(self, context_xml: str) -> str:
        completed = self._parse_completed(context_xml)
        pipeline = pipeline_for_style(self._style_mode)
        for action in pipeline:
            step_type = ACTION_TO_STEP[action]
            if step_type not in completed:
                meta = STEP_META[step_type]
                thought = f"委派 {meta['title']}"
                return format_react_xml(thought, action)
        return format_react_xml("全部完成", "finish")

    def _sub_agent_react(self, log_ctx: dict[str, Any], context_xml: str) -> str:
        agent_name = str(log_ctx.get("agent_name", ""))
        completed = self._parse_completed(context_xml)
        pipeline = self._pipeline_for_agent(agent_name)
        for action in pipeline:
            if action not in completed:
                thought = f"[{agent_name}] 执行 {action}"
                return format_react_xml(thought, action)
        return format_react_xml("任务完成", "finish")

    def _pipeline_for_agent(self, agent_name: str) -> list[str]:
        from core.agents.definitions import AGENT_DEFINITIONS

        definition = AGENT_DEFINITIONS.get(agent_name)
        return list(definition.action_pipeline) if definition else []

    def _parse_completed(self, context_xml: str) -> set[str]:
        completed: set[str] = set()
        for tag in ("completed_actions", "completed"):
            block = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", context_xml)
            if not block:
                continue
            for item in re.findall(r"<item>([\s\S]*?)</item>", block.group(1)):
                text = item.strip()
                if text and text != "无":
                    if text.startswith("tool:"):
                        continue
                    completed.add(text)
        return completed

    async def complete_json(
        self,
        system_prompt: str,
        user_content: str,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM JSON",
        on_delta: Any = None,
        response_format: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        action_match = re.search(r"当前行动：(\S+)", user_content)
        if action_match:
            return _scripted_action_json(action_match.group(1))

        ctx = log_context or {}
        role = ctx.get("role", "")
        if role == "intent_gate":
            return _scripted_intent_json(user_content)

        completed = _parse_completed_json(user_content)
        if role == "master":
            return self._master_react_json(completed)
        if role == "sub_agent":
            return self._sub_agent_react_json(str(ctx.get("agent_name", "")), completed)

        try:
            data = json.loads(user_content)
        except json.JSONDecodeError:
            return _format_react_json("默认结束", "finish")

        for action in data.get("available_actions", []):
            if action not in completed and action != "finish":
                return _format_react_json(f"执行 {action}", action)
        return _format_react_json("完成", "finish")

    def _master_react_json(self, completed: set[str]) -> dict[str, Any]:
        pipeline = pipeline_for_style(self._style_mode)
        for action in pipeline:
            step_type = ACTION_TO_STEP[action]
            if step_type not in completed:
                meta = STEP_META[step_type]
                return _format_react_json(f"委派 {meta['title']}", action)
        return _format_react_json("全部完成", "finish")

    def _sub_agent_react_json(
        self, agent_name: str, completed: set[str]
    ) -> dict[str, Any]:
        pipeline = self._pipeline_for_agent(agent_name)
        for action in pipeline:
            if action not in completed:
                return _format_react_json(f"[{agent_name}] 执行 {action}", action)
        return _format_react_json("任务完成", "finish")

    async def complete_text(
        self,
        system_prompt: str,
        user_content: str,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM 文本",
        on_delta: Any = None,
    ) -> str:
        text = "已完成视频制作流程，剧本与资产已生成，可在右侧查看具体内容。"
        if on_delta:
            for char in text:
                await on_delta(char)
        return text


def _scripted_intent_json(user_content: str) -> dict[str, Any]:
    """测试用意图门卫：默认放行，仅明显离题消息拒绝。"""
    match = re.search(r"用户消息：(.+)", user_content, re.S)
    message = (match.group(1).strip() if match else user_content).strip()
    off_topic_markers = ("今天天气", "股票价格", "写一段python", "编程作业")
    if any(marker in message.lower() for marker in off_topic_markers):
        return {
            "in_scope": False,
            "reason": "与视频制作无关",
            "reply": "抱歉，我只能处理视频生成相关的请求。请描述您的视频创意。",
        }
    return {"in_scope": True, "reason": "属于视频制作或创意描述", "reply": ""}


def _parse_completed_json(user_content: str) -> set[str]:
    try:
        data = json.loads(user_content)
    except json.JSONDecodeError:
        return set()
    completed: set[str] = set()
    for item in data.get("completed_actions", []):
        text = str(item).strip()
        if text and text != "无" and not text.startswith("tool:"):
            completed.add(text)
    return completed


def _format_react_json(
    thought: str, action: str, action_input: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"thought": thought, "action": action, "action_input": action_input or {}}


def _scripted_action_json(action: str) -> dict[str, Any]:
    """与原先 Mock 行为等价的 JSON 结果（由 apply_action_result 落盘）。"""
    mapping: dict[str, dict[str, Any]] = {
        "parse_brief": {
            "observation": "已解析任务简报。",
            "script_md": "# 测试剧本\n\n基于任务简报生成的内容。",
        },
        "create_plot": {
            "observation": "已创建剧情资产。",
            "asset_name": "剧情段落1",
            "content": {"text": "主角登场，故事开始。"},
        },
        "create_character": {
            "observation": "已创建人物资产。",
            "asset_name": "主角",
            "content": {"appearance": "年轻女性，短发"},
        },
        "create_scene": {
            "observation": "已创建场景资产。",
            "asset_name": "城市街道",
            "content": {"description": "现代都市黄昏"},
        },
        "update_script": {
            "observation": "已更新剧本正文。",
            "script_md": "# 测试剧本\n\n更新后的内容。",
        },
        "update_plot": {
            "observation": "已更新剧情。",
            "asset_id": "plot_existing",
            "content": {"text": "修订后的剧情。"},
        },
        "delete_scene": {
            "observation": "已删除场景。",
            "asset_id": "scene_to_delete",
        },
        "scan_text_assets": {"observation": "扫描完成。", "count": 2},
        "generate_images": {"observation": "图片已生成。"},
        "load_context": {"observation": "上下文已加载。", "asset_count": 3},
        "create_shots": {
            "observation": "镜头已设计。",
            "shots": [
                {"order": 0, "duration_ms": 3000, "narration_text": "开场", "camera_motion": "ken_burns_in"},
                {"order": 1, "duration_ms": 4000, "narration_text": "发展", "camera_motion": "pan_right"},
                {"order": 2, "duration_ms": 3000, "narration_text": "结尾", "camera_motion": "fade"},
            ],
        },
        "persist_plan": {"observation": "计划稿已保存。"},
        "load_shots": {
            "observation": "镜头已加载。",
            "shot_count": 3,
            "estimated_cost_usd": VIDEO_GEN_COST_PER_SHOT_USD * 3,
        },
        "generate_clips": {"observation": "视频片段已生成。"},
        "extract_narration": {"observation": "旁白已提取。", "line_count": 3},
        "synthesize": {
            "observation": "配音已合成。",
            "asset_id": "tts_test",
            "url": "/assets/narration.mp3",
            "label": "narration",
        },
        "gather_media": {"observation": "素材已收集。", "summary": "已收集全部素材。"},
        "compose_final": {
            "observation": "成片已合成。",
            "asset_id": "fin_test",
            "url": "/assets/fin_test.mp4",
            "label": "final_video",
        },
    }
    return mapping.get(action, {"observation": f"已完成 {action}。"})
