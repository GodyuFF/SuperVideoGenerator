"""测试用脚本化 LLM 客户端：不发起真实 HTTP，按流水线返回确定性响应。"""

import json
import re
from typing import Any

from core.llm.client.tool_calls import ToolCallResult
from core.models.entities import VideoStyleMode
from core.llm.model.llm_request import LlmRequest
from core.llm.master import STEP_META
from core.llm.master.delegate_deps import delegates_for_style
from core.llm.master.delegate_tool import DELEGATE_AGENT_ACTION, steps_for_style
from core.llm.client.token_round import TokenRoundAccumulator

# 测试脚本 LLM 用稳定委派顺序（按 step_type，非字母序）
_SCRIPTED_STEP_ORDER = [
    "script_design",
    "storyboard",
    "image_gen",
    "video_gen",
    "tts_gen",
    "shot_detail",
    "edit_compose",
]
from core.llm.client.tokens import TokenEstimate
from core.llm.model.chat_message import ChatMessage
from core.llm.prompt.chat_messages import extract_react_state_json, last_user_content


class ScriptedLLMClient:
    """模拟 LLMClient.complete / complete_tool_calls，供单元测试使用。"""

    def __init__(self, style_mode: VideoStyleMode = VideoStyleMode.STORYBOOK) -> None:
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
            thought, action, args = self._master_react_tool(state, completed)
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
                args: dict[str, Any] = {}
                for name in state.get("available_actions", []):
                    if name not in completed and name != "finish":
                        action = name
                        thought = f"执行 {action}"
                        args = _args_for_available_action(state, completed, name)
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
                            args = _args_for_available_action(data, completed, name)
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

    def _master_react_tool(
        self,
        state: dict[str, Any],
        completed: set[str],
    ) -> tuple[str, str, dict[str, Any]]:
        if DELEGATE_AGENT_ACTION not in delegates_for_style(self._style_mode):
            return "全部完成", "finish", {}
        completed_steps = _completed_step_types(completed)
        args = _pick_delegate_args(state, completed_steps, self._style_mode)
        agent_id = args.get("agent_id")
        if not agent_id:
            return "全部完成", "finish", {}
        step_type = _step_type_for_agent(agent_id)
        title = STEP_META.get(step_type or "", {}).get("title", agent_id)
        return f"委派 {title}", DELEGATE_AGENT_ACTION, args

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
        from core.llm.master.actions import (
            filter_storyboard_pipeline_actions,
            filter_video_pipeline_actions,
        )

        definition = AGENT_DEFINITIONS.get(agent_name)
        pipeline = list(definition.action_pipeline) if definition else []
        if agent_name == "storyboard_agent":
            return filter_storyboard_pipeline_actions(pipeline, self._style_mode)
        if agent_name == "video_agent":
            return filter_video_pipeline_actions(pipeline)
        return pipeline

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


def _step_type_for_agent(agent_id: str) -> str | None:
    for step_type, meta in STEP_META.items():
        if meta.get("agent") == agent_id:
            return step_type
    return None


def _completed_step_types(completed: set[str]) -> set[str]:
    """从 completed_actions 解析已完成 step_type。"""
    steps: set[str] = set()
    for item in completed:
        if item.startswith("step:"):
            steps.add(item[5:])
        elif item in STEP_META:
            steps.add(item)
    return steps


def _next_scripted_agent_id(
    style_mode: VideoStyleMode,
    completed_steps: set[str],
) -> str | None:
    allowed = set(steps_for_style(style_mode))
    for step_type in _SCRIPTED_STEP_ORDER:
        if step_type not in allowed:
            continue
        if step_type in completed_steps:
            continue
        return STEP_META[step_type]["agent"]
    return None


def _pick_delegate_args(
    state: dict[str, Any],
    completed_steps: set[str],
    style_mode: VideoStyleMode,
) -> dict[str, Any]:
    readiness = state.get("delegate_readiness") or []
    for row in readiness:
        step_type = str(row.get("step_type") or "")
        agent_id = row.get("agent_id")
        if not agent_id or step_type in completed_steps or row.get("hard_blockers"):
            continue
        return {"agent_id": str(agent_id)}
    agent_id = _next_scripted_agent_id(style_mode, completed_steps)
    return {"agent_id": agent_id} if agent_id else {}


def _args_for_available_action(
    state: dict[str, Any],
    completed: set[str],
    action: str,
) -> dict[str, Any]:
    if action != DELEGATE_AGENT_ACTION:
        return {}
    return _pick_delegate_args(state, _completed_step_types(completed), VideoStyleMode.STORYBOOK)


def _make_tool_call(name: str, arguments: dict[str, Any], *, call_id: str = "") -> dict[str, Any]:
    args = dict(arguments)
    if "plan_status" not in args:
        args["plan_status"] = f"scripted: 已选择 {name}"
    if "remaining_plan" not in args:
        args["remaining_plan"] = [] if name == "finish" else [f"继续 {name} 后续步骤"]
    return {
        "id": call_id or f"call_scripted_{name}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


_SCRIPTED_BATCH_CREATES = frozenset(
    {"create_plot", "create_character", "create_scene", "create_prop"}
)


def _make_tool_calls(actions: list[str]) -> list[dict[str, Any]]:
    """批量构造 scripted tool_calls（测试同轮多 tool 并行）。"""
    return [
        _make_tool_call(
            action,
            _scripted_action_json(action),
            call_id=f"call_scripted_{idx}_{action}",
        )
        for idx, action in enumerate(actions)
    ]


def _scripted_sub_agent_tool_calls(
    agent_name: str,
    completed: set[str],
    pipeline: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    """子 Agent scripted 响应：parse_brief 后剩余 create_* 可同轮 batch 返回。"""
    pending = [action for action in pipeline if action not in completed]
    if not pending:
        return "任务完成", [_make_tool_call("finish", {})]
    if agent_name == "script_agent" and "parse_brief" in completed:
        batch = [action for action in pending if action in _SCRIPTED_BATCH_CREATES]
        if len(batch) > 1:
            return (
                f"[{agent_name}] 批量执行 {len(batch)} 个 create",
                _make_tool_calls(batch),
            )
    action = pending[0]
    return (
        f"[{agent_name}] 执行 {action}",
        [_make_tool_call(action, _scripted_action_json(action))],
    )


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
                tts_voice="zh-CN-XiaoxiaoNeural-Female",
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
        "load_context": {
            "observation": "上下文已加载。",
            "script_id": "script_fixture",
            "asset_count": 3,
        },
        "create_shots": {
            "observation": "镜头已设计。",
            "shots": [
                {
                    "order": 0,
                    "duration_ms": 3000,
                    "sub_shots": [
                        {
                            "id": "ssb_scripted_0",
                            "start_ms": 0,
                            "end_ms": 3000,
                            "description": "开场",
                            "camera_motion": "ken_burns_in",
                        }
                    ],
                    "audio_tracks": [
                        {
                            "kind": "voice",
                            "name": "角色音",
                            "clips": [{"start_ms": 0, "end_ms": 3000, "text": "开场"}],
                        }
                    ],
                },
                {
                    "order": 1,
                    "duration_ms": 4000,
                    "sub_shots": [
                        {
                            "id": "ssb_scripted_1",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "description": "发展",
                            "camera_motion": "pan_right",
                        }
                    ],
                    "audio_tracks": [
                        {
                            "kind": "voice",
                            "name": "角色音",
                            "clips": [{"start_ms": 0, "end_ms": 4000, "text": "发展"}],
                        }
                    ],
                },
                {
                    "order": 2,
                    "duration_ms": 3000,
                    "sub_shots": [
                        {
                            "id": "ssb_scripted_2",
                            "start_ms": 0,
                            "end_ms": 3000,
                            "description": "结尾",
                            "camera_motion": "fade",
                        }
                    ],
                    "audio_tracks": [
                        {
                            "kind": "voice",
                            "name": "角色音",
                            "clips": [{"start_ms": 0, "end_ms": 3000, "text": "结尾"}],
                        }
                    ],
                },
            ],
        },
        "create_frames": {
            "observation": "剧本画面 frame 已创建。",
            "frames": [
                {
                    "order": 0,
                    "sub_shot_id": "ssb_scripted_0",
                    "description": "开场画面，无人物纯背景或合成画面",
                },
                {
                    "order": 1,
                    "sub_shot_id": "ssb_scripted_1",
                    "description": "发展段落画面",
                },
                {
                    "order": 2,
                    "sub_shot_id": "ssb_scripted_2",
                    "description": "结尾画面",
                },
            ],
        },
        "create_video_clips": {
            "observation": "video_clip 文字资产已创建。",
            "video_clips": [
                {
                    "order": 0,
                    "sub_shot_id": "ssb_scripted_0",
                    "description": "开场 AI 视频片段",
                    "element_refs": {},
                },
                {
                    "order": 1,
                    "sub_shot_id": "ssb_scripted_1",
                    "description": "发展段落 AI 视频",
                    "element_refs": {},
                },
                {
                    "order": 2,
                    "sub_shot_id": "ssb_scripted_2",
                    "description": "结尾 AI 视频",
                    "element_refs": {},
                },
            ],
        },
        "persist_plan": {"observation": "计划稿已保存。"},
        "get_shot_details": {"observation": "分镜详情已查询。"},
        "get_shot_asset_timing": {"observation": "资产时长已查询。", "asset_kind": "all"},
        "sync_actual_assets": {"observation": "已同步实测资产时长。"},
        "review_shot": {
            "observation": "单镜复核",
            "plan_status": "测试中",
            "remaining_plan": ["finish"],
            "shot_id": "shot_scripted_0",
            "patch": {"display_instructions": "测试展示说明"},
        },
        "review_and_restructure": {
            "observation": "已复核分镜。",
            "restructure_ops": [],
            "patches": [
                {
                    "shot_id": "shot_scripted_0",
                    "display_instructions": "Ken Burns 缓慢推近主体",
                    "camera_motion_refined": "ken_burns_in",
                }
            ],
        },
        "persist_review": {"observation": "复核结果已保存。"},
        "update_frames": {"observation": "frame 备注已更新。"},
        "load_shots": {
            "observation": "镜头已加载。",
            "shot_count": 3,
        },
        "scan_video_clips": {
            "observation": "已扫描 video_clip。",
            "total": 3,
            "ready": 3,
        },
        "generate_video_clips": {"observation": "video_clip 视频已生成。"},
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
