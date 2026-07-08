"""测试用脚本化 LLM 客户端：不发起真实 HTTP，按流水线返回确定性响应。"""

import json
import re
from typing import Any

from core.llm.client.tool_calls import ToolCallResult
from core.models.entities import VideoStyleMode
from core.llm.model.llm_request import LlmRequest
from core.llm.master import ACTION_TO_STEP, STEP_META, pipeline_for_style
from core.llm.client.token_round import TokenRoundAccumulator
from core.llm.client.tokens import TokenEstimate
from core.llm.model.chat_message import ChatMessage
from core.llm.prompt.chat_messages import extract_react_state_json, last_user_content


class ScriptedLLMClient:
    """模拟 LLMClient.complete / complete_tool_calls，供单元测试使用。"""

    def __init__(self, style_mode: VideoStyleMode = VideoStyleMode.DYNAMIC_IMAGE) -> None:
        self._style_mode = style_mode
        self._token_round: TokenRoundAccumulator | None = None

    def begin_token_round(
        self,
        *,
        conversation_id: str,
        project_id: str,
        script_id: str,
    ) -> None:
        self._token_round = TokenRoundAccumulator(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
        )

    def end_token_round(self) -> dict[str, Any] | None:
        if not self._token_round:
            return None
        snapshot = self._token_round.snapshot()
        self._token_round = None
        return snapshot

    def _record_scripted_tokens(self) -> None:
        if not self._token_round:
            return
        self._token_round.add(
            "scripted",
            "scripted-model",
            TokenEstimate(prompt_tokens=120, completion_tokens=80, total_tokens=200),
        )

    async def complete_tool_calls(
        self,
        request: LlmRequest,
        *,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM tool_calls",
        on_delta: Any = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        ctx = log_context or {}
        role = str(ctx.get("role", ""))
        forced_action = ""
        if request.tool_choice:
            if request.tool_choice.get("type") == "tool":
                forced_action = str(request.tool_choice.get("name", "")).strip()
            else:
                forced_action = str(
                    (request.tool_choice.get("function") or {}).get("name", "")
                ).strip()
        if not forced_action:
            forced_action = str(ctx.get("action", "")).strip()

        turn_content = last_user_content(request)
        system_content = request.system or ""
        action_match = re.search(r"当前行动：(\S+)", system_content) or re.search(
            r"当前行动：(\S+)", turn_content
        )

        if role == "agent_action" or action_match or forced_action:
            action = forced_action or (action_match.group(1) if action_match else "finish")
            args = _scripted_action_json(action)
            thought = f"执行 {action}"
            tool_calls = [_make_tool_call(action, args)]
        elif role == "master":
            state = extract_react_state_json(request) or {}
            completed = _parse_completed_from_state(state)
            thought, action, args = self._master_react_tool(completed)
            tool_calls = [_make_tool_call(action, args)]
        elif role == "sub_agent":
            state = extract_react_state_json(request) or {}
            completed = _parse_completed_from_state(state)
            thought, action, args = self._sub_agent_react_tool(
                str(ctx.get("agent_name", "")), completed
            )
            tool_calls = [_make_tool_call(action, args)]
        else:
            state = extract_react_state_json(request) or {}
            completed = _parse_completed_from_state(state)
            if state:
                action = "finish"
                thought = "完成"
                args = {}
                for name in state.get("available_actions", []):
                    if name not in completed and name != "finish":
                        action = name
                        thought = f"执行 {action}"
                        args = {}
                        break
            else:
                try:
                    data = json.loads(turn_content)
                except json.JSONDecodeError:
                    thought, action, args = "默认结束", "finish", {}
                else:
                    action = "finish"
                    thought = "完成"
                    args = {}
                    for name in data.get("available_actions", []):
                        if name not in completed and name != "finish":
                            action = name
                            thought = f"执行 {action}"
                            args = {}
                            break
            tool_calls = [_make_tool_call(action, args)]

        if on_delta and thought:
            for char in thought:
                await on_delta(char)
        self._record_scripted_tokens()
        return ToolCallResult(
            content=thought,
            tool_calls=tool_calls,
            raw_message={
                "role": "assistant",
                "content": thought,
                "tool_calls": tool_calls,
            },
        )

    def _master_react_tool(self, completed: set[str]) -> tuple[str, str, dict[str, Any]]:
        pipeline = pipeline_for_style(self._style_mode)
        for action in pipeline:
            if action not in completed:
                meta = STEP_META[ACTION_TO_STEP[action]]
                return f"委派 {meta['title']}", action, {}
        return "全部完成", "finish", {}

    def _sub_agent_react_tool(
        self, agent_name: str, completed: set[str]
    ) -> tuple[str, str, dict[str, Any]]:
        pipeline = self._pipeline_for_agent(agent_name)
        for action in pipeline:
            if action not in completed:
                return f"[{agent_name}] 执行 {action}", action, {}
        return "任务完成", "finish", {}

    def _pipeline_for_agent(self, agent_name: str) -> list[str]:
        from core.llm.agent.definitions import AGENT_DEFINITIONS

        definition = AGENT_DEFINITIONS.get(agent_name)
        return list(definition.action_pipeline) if definition else []

    async def complete_json(
        self,
        request: LlmRequest,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM JSON",
        on_delta: Any = None,
        response_format: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """摘要等非 ReAct 场景仍返回 JSON 对象。"""
        text = "已完成视频制作流程，剧本与资产已生成，可在右侧查看具体内容。"
        if on_delta:
            for char in text:
                await on_delta(char)
        self._record_scripted_tokens()
        return {"summary": text}

    async def complete(
        self,
        request: LlmRequest,
        log_context: dict[str, Any] | None = None,
        summary_prefix: str = "LLM",
        on_delta: Any = None,
        response_format: Any = None,
        response_kind: str = "text",
    ) -> str:
        text = "已完成视频制作流程，剧本与资产已生成，可在右侧查看具体内容。"
        if on_delta:
            for char in text:
                await on_delta(char)
        self._record_scripted_tokens()
        return text


def _make_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args = dict(arguments)
    if "plan_status" not in args:
        args["plan_status"] = f"scripted: 已选择 {name}"
    if "remaining_plan" not in args:
        args["remaining_plan"] = [] if name == "finish" else [f"继续 {name} 后续步骤"]
    return {
        "id": f"call_scripted_{name}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


def _parse_completed_from_state(state: dict[str, Any]) -> set[str]:
    completed: set[str] = set()
    for item in state.get("completed_actions", []):
        text = str(item).strip()
        if text and text != "无" and not text.startswith("tool:"):
            completed.add(text)
    return completed


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


from tests.support.image_text_fixtures import (
    character_content,
    prop_content,
    scene_content,
)


def _scripted_action_json(action: str) -> dict[str, Any]:
    """与原先 Mock 行为等价的 tool arguments。"""
    mapping: dict[str, dict[str, Any]] = {
        "parse_brief": {
            "observation": "已解析任务简报。",
            "content_md": "# 测试剧本\n\n基于任务简报生成的内容。",
        },
        "create_plot": {
            "observation": "已创建剧情资产。",
            "asset_name": "剧情段落1",
            "content": {"text": "主角登场，故事开始。"},
        },
        "create_character": {
            "observation": "已创建人物资产。",
            "asset_name": "主角",
            "content": character_content(
                summary="短发女主角",
                description=(
                    "年轻女性，黑色短发，穿都市休闲装，站在霓虹灯下的街道，"
                    "神情专注，整体气质干练而温和。"
                ),
                role="主角",
            ),
        },
        "create_scene": {
            "observation": "已创建场景资产。",
            "asset_name": "城市街道",
            "content": scene_content(
                summary="都市黄昏",
                description=(
                    "现代都市黄昏街道，霓虹初上，湿润路面反射灯光，"
                    "两侧商铺立面与玻璃幕墙，远处高楼天际线，空旷无人。"
                ),
                location="城市街道",
                time_of_day="黄昏",
            ),
        },
        "create_prop": {
            "observation": "已创建道具资产。",
            "asset_name": "旧相机",
            "content": prop_content(
                summary="复古相机",
                description=(
                    "银色复古胶片相机，金属机身有轻微划痕，皮质肩带，"
                    "镜头反光可见环境，适合作为叙事道具特写。"
                ),
                category="日用品",
            ),
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
        "create_frames": {
            "observation": "画面资产已创建。",
            "frames": [
                {"order": 0, "description": "开场画面，无人物纯背景或合成画面"},
                {"order": 1, "description": "发展段落画面"},
                {"order": 2, "description": "结尾画面"},
            ],
        },
        "persist_plan": {"observation": "计划稿已保存。"},
        "load_shots": {
            "observation": "镜头已加载。",
            "shot_count": 3,
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
