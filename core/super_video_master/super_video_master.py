"""超级视频大师主 Agent：ReAct 编排，与用户及子 Agent 对话隔离。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.llm.a2ui.manager import ConfirmationManager, ConfirmationRejectedError
from core.conversation import ConversationIndex, ConversationStore
from core.super_video_master import MASTER_AGENT_NAME
from core.llm.master import MasterReActEngine
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.logging.perf import log_perf
from core.logging.setup import get_logger, log_stage
from core.guards.script_style import (
    bind_script_style,
    bind_script_style_hints,
)
from core.super_video_master.clarification import (
    has_script_duration_context,
    should_request_script_requirements,
)
from core.llm.execution_mode import is_goal_mode
from core.llm.prompt.skills import load_skill, parse_skill_command
from core.llm.client import LLMClient
from core.llm.client.settings import LLMConfigManager
from core.models.entities import ExecutionMode, GenerationMode, ScriptStatus, VideoStyleMode
from core.llm.agent.config_manager import get_agent_config_manager
from core.llm.agent.registry import AgentRegistry
from core.store.memory import MemoryStore

if TYPE_CHECKING:
    from core.llm.agent.config_manager import AgentConfigManager

logger = get_logger("core.super_video_master")


class SuperVideoMaster:
    """主编排器（超级视频大师）：主会话 ReAct + 向子 Agent 下发隔离任务简报。"""

    def __init__(
            self,
            store: MemoryStore,
            emitter: EventEmitter,
            confirmation_manager: ConfirmationManager,
            conversations: ConversationStore | None = None,
            llm_config: LLMConfigManager | None = None,
            interaction_recorder: InteractionRecorder | None = None,
            agent_config: AgentConfigManager | None = None,
            conversation_index: ConversationIndex | None = None,
    ) -> None:
        self._store = store
        self._emitter = emitter
        self._confirmation = confirmation_manager
        self._conversations = conversations or ConversationStore()
        self._conversation_index = conversation_index or ConversationIndex()
        self._llm_config = llm_config or LLMConfigManager()
        self._recorder = interaction_recorder
        self._llm_client = LLMClient(self._llm_config, self._recorder)
        self._agent_config = agent_config or get_agent_config_manager()
        self._registry = AgentRegistry(
            store,
            emitter,
            self._conversations,
            self._llm_config,
            self._llm_client,
            self._recorder,
            self._agent_config,
            confirmation_manager,
        )
        self._react = MasterReActEngine(
            store,
            emitter,
            self._registry,
            self._conversations,
            confirmation_manager,
            self._llm_config,
            self._llm_client,
        )

    def rebind_conversation_stores(
        self,
        conversations: ConversationStore,
        conversation_index: ConversationIndex,
    ) -> None:
        """重绑对话仓储引用，使编排链路与 AppState 使用同一 ConversationStore。"""
        self._conversations = conversations
        self._conversation_index = conversation_index
        self._react._conversations = conversations
        for agent in self._registry._agents.values():
            agent._conversations = conversations

    def _active_llm_client(self) -> LLMClient:
        """主编排与子 Agent 共用的 LLM 客户端（token 轮次绑定此实例）。"""
        return self._react._llm_client

    async def _finalize_token_round(
        self,
        conversation_id: str,
        project_id: str,
        script_id: str,
    ) -> None:
        token_usage = self._active_llm_client().end_token_round()
        if not token_usage:
            return
        self._conversation_index.record_token_round(conversation_id, token_usage)
        if self._recorder:
            await self._recorder.record_conversation_token_round(
                project_id=project_id,
                script_id=script_id,
                conversation_id=conversation_id,
                usage=token_usage,
            )

    async def _emit_llm_summary(
        self,
        project_id: str,
        script_id: str,
        conversation_id: str,
        content: str,
    ) -> None:
        self._conversations.add_assistant_summary(
            conversation_id,
            project_id,
            script_id,
            content,
        )
        await self._emitter.emit(
            {
                "type": "master_message",
                "script_id": script_id,
                "conversation_id": conversation_id,
                "role": "super_video_master",
                "agent_name": MASTER_AGENT_NAME,
                "content": content,
                "source": "llm_summary",
            }
        )

    def _ensure_conversation(
        self,
        project_id: str,
        script_id: str,
        conversation_id: str | None,
        *,
        title: str = "",
    ) -> str:
        if conversation_id:
            self._conversation_index.require(
                conversation_id,
                project_id=project_id,
                script_id=script_id,
            )
            return conversation_id
        conv = self._conversation_index.create(
            project_id,
            script_id,
            title=title,
        )
        return conv.id

    async def run_from_message(
            self,
            project_id: str,
            script_id: str,
            message: str,
            requested_style: VideoStyleMode | None = None,
            requested_hints: dict[str, str] | None = None,
            conversation_id: str | None = None,
            execution_mode: ExecutionMode | None = None,
            skill_id: str | None = None,
    ) -> tuple[str, str]:
        """
        对话入口：用户消息仅进入主会话；子 Agent 通过任务简报隔离调用。
        返回本次对话的 conversation_id 与用户可见结束摘要。
        """
        script = self._store.get_script(script_id)
        project = self._store.get_project(project_id)
        if not script or not project:
            raise ValueError("项目或剧本不存在")
        if script.status == ScriptStatus.EXECUTING:
            raise ValueError("剧本正在执行中，请稍候")

        run_start = time.perf_counter()
        user_text = message.strip()
        parsed_skill_id, parsed_rest = parse_skill_command(user_text)
        active_skill_id = skill_id or parsed_skill_id
        skill_bundle = load_skill(active_skill_id) if active_skill_id else None
        if active_skill_id and skill_bundle is None:
            err = f"未知 Skill「{active_skill_id}」，请使用 /skillId 或查看可用 Skill 列表。"
            conversation_id = self._ensure_conversation(
                project_id,
                script_id,
                conversation_id,
                title=user_text[:48],
            )
            self._conversations.add_assistant_summary(
                conversation_id, project_id, script_id, err
            )
            return conversation_id, err

        if user_text.startswith("/") and not active_skill_id:
            token = user_text[1:].strip().split(None, 1)[0].lower() if user_text[1:].strip() else ""
            if token:
                err = f"未知 Skill「{token}」，请使用 /skillId 或查看可用 Skill 列表。"
                conversation_id = self._ensure_conversation(
                    project_id,
                    script_id,
                    conversation_id,
                    title=user_text[:48],
                )
                self._conversations.add_assistant_summary(
                    conversation_id, project_id, script_id, err
                )
                return conversation_id, err

        if skill_bundle:
            rest = parsed_rest if parsed_skill_id else user_text
            prefix = skill_bundle.format_task_prefix()
            user_text = f"{prefix}\n\n用户诉求：{rest}" if rest else prefix

        goal = is_goal_mode(project, override=execution_mode)
        # 对话线程标题优先用已确认的剧本标题，禁止用每轮用户消息摘要覆盖剧本名
        preview = user_text.replace("\n", " ")
        if len(preview) > 48:
            preview = preview[:48] + "…"
        conversation_title = (script.title or "").strip() or preview
        conversation_id = self._ensure_conversation(
            project_id,
            script_id,
            conversation_id,
            title=conversation_title,
        )

        # 1. A2UI 需求补全（已有剧本正文，或风格+时长已知时可跳过）
        style_known = (
                requested_style is not None
                or script.style_locked
                or project.config.style.mode is not None
        )
        duration_known = has_script_duration_context(
            user_text=user_text,
            script_duration_sec=script.duration_sec,
            script_style_hints=script.style_hints,
            requested_hints=requested_hints,
        )
        has_existing_script_body = bool((script.content_md or "").strip())
        needs_clarification = should_request_script_requirements(
            goal=goal,
            style_known=style_known,
            has_duration_context=duration_known,
            has_existing_script_body=has_existing_script_body,
        )

        if needs_clarification:
            try:
                req_response = await self._confirmation.request_script_requirements(
                    script_id=script_id,
                    initial_message=user_text,
                    conversation_id=conversation_id,
                    default_duration_sec=script.duration_sec or 60,
                    default_style_mode=(
                        requested_style.value
                        if requested_style is not None
                        else (
                            project.config.style.mode.value
                            if project.config.style.mode is not None
                            else "storybook"
                        )
                    ),
                )
                # 用户已通过 A2UI 补充信息，将表单值合并到 user_text
                values = req_response.values or {}
                clarified_parts = []
                if values.get("theme"):
                    clarified_parts.append(str(values["theme"]))
                if values.get("duration_sec"):
                    clarified_parts.append(f"目标时长 {values['duration_sec']}s")
                if values.get("style_mode"):
                    clarified_parts.append(f"风格 {values['style_mode']}")
                if values.get("main_characters"):
                    clarified_parts.append(f"人物：{values['main_characters']}")
                if values.get("main_scenes"):
                    clarified_parts.append(f"场景：{values['main_scenes']}")

                if clarified_parts:
                    user_text = "；".join(clarified_parts)
                    log_stage(
                        logger,
                        "super_video_master",
                        "已通过 A2UI 收集剧本需求",
                        script_id=script_id,
                    )
            except ConfirmationRejectedError:
                cancel_msg = "已取消剧本生成。"
                self._conversations.add_assistant_summary(
                    conversation_id,
                    project_id,
                    script_id,
                    cancel_msg,
                )
                self._conversation_index.touch_after_message(
                    conversation_id, last_summary="已取消。"
                )
                return conversation_id, "已取消。"

        # 2. 绑定视频风格与可选提示词到剧本（提示词随风格一并锁定）
        style_hints = bind_script_style_hints(script, requested_hints)
        style_mode = bind_script_style(script, project, requested_style)
        await self._emitter.emit(
            {
                "type": "script_style_locked",
                "script_id": script_id,
                "style_mode": style_mode,
                "style_hints": style_hints,
            }
        )
        log_stage(
            logger,
            "super_video_master",
            "剧本视频风格已绑定",
            script_id=script_id,
            style_mode=style_mode,
        )

        # 3. 主会话记录用户消息（ConversationStore master 通道）
        self._conversations.add_user_message(
            conversation_id,
            project_id,
            script_id,
            user_text,
        )
        self._conversation_index.touch_after_message(
            conversation_id, title=conversation_title
        )

        log_stage(
            logger,
            "super_video_master",
            "ReAct 对话驱动开始",
            script_id=script_id,
            conversation_id=conversation_id,
        )
        from core.execution.cancel import get_execution_cancel_registry

        cancel_registry = get_execution_cancel_registry()
        cancel_registry.register(script_id, conversation_id)
        self._active_llm_client().begin_token_round(
            conversation_id=conversation_id,
            project_id=project_id,
            script_id=script_id,
        )
        user_aborted = False
        try:
            observations = await self._react.run(
                project_id=project_id,
                script_id=script_id,
                user_message=user_text,
                style_mode=style_mode,
                generation_mode=project.config.generation.mode,
                conversation_id=conversation_id,
                execution_mode=execution_mode,
                skill_overlay=(
                    {
                        "id": skill_bundle.meta.id,
                        "title": skill_bundle.meta.title,
                        "agent_overlays": dict(skill_bundle.agent_overlays),
                        "tool_manifest": (
                            skill_bundle.tool_manifest.to_dict()
                            if skill_bundle.tool_manifest
                            else None
                        ),
                        "mcp_servers": (
                            list(skill_bundle.tool_manifest.mcp_servers)
                            if skill_bundle.tool_manifest
                            and skill_bundle.tool_manifest.mcp_servers
                            else []
                        ),
                    }
                    if skill_bundle
                    else None
                ),
            )
        except Exception as e:
            await self._finalize_token_round(conversation_id, project_id, script_id)
            fail_summary = f"执行失败：{e}"
            self._conversations.add_assistant_summary(
                conversation_id,
                project_id,
                script_id,
                fail_summary,
            )
            self._conversation_index.touch_after_message(
                conversation_id, last_summary=fail_summary
            )
            log_stage(
                logger,
                "super_video_master",
                "ReAct 对话驱动异常结束",
                script_id=script_id,
                error=str(e),
                conversation_id=conversation_id,
            )
            return conversation_id, fail_summary
        finally:
            user_aborted = cancel_registry.is_cancelled(script_id)
            cancel_registry.clear(script_id)

        if user_aborted:
            await self._finalize_token_round(conversation_id, project_id, script_id)
            abort_summary = "已中止执行。"
            self._conversations.add_assistant_summary(
                conversation_id,
                project_id,
                script_id,
                abort_summary,
            )
            self._conversation_index.touch_after_message(
                conversation_id, last_summary=abort_summary
            )
            log_stage(
                logger,
                "super_video_master",
                "用户中止主编排",
                script_id=script_id,
                conversation_id=conversation_id,
            )
            return conversation_id, abort_summary

        script = self._store.get_script(script_id)
        if script and script.status == ScriptStatus.FAILED:
            summary = "执行未能完成，请查看右侧计划步骤或错误日志。"
            self._conversations.add_assistant_summary(
                conversation_id,
                project_id,
                script_id,
                summary,
            )
            self._conversation_index.touch_after_message(
                conversation_id, last_summary=summary
            )
            await self._finalize_token_round(conversation_id, project_id, script_id)
            log_stage(
                logger,
                "super_video_master",
                "ReAct 对话驱动失败结束",
                script_id=script_id,
                status=script.status.value,
                conversation_id=conversation_id,
            )
            return conversation_id, summary

        # 4. LLM 生成用户可见结束摘要
        from core.super_video_master.summary import generate_user_summary

        stream_id = f"summary-{conversation_id}"
        await self._emitter.emit(
            {
                "type": "llm_stream_start",
                "script_id": script_id,
                "stream_id": stream_id,
                "kind": "llm_summary",
                "source": "llm_summary",
                "visibility": "user",
                "conversation_id": conversation_id,
                "agent_name": MASTER_AGENT_NAME,
            }
        )

        from core.llm.client.stream_delta_batcher import make_batched_delta_handler

        async def emit_summary_delta(delta: str) -> None:
            await self._emitter.emit(
                {
                    "type": "llm_stream_delta",
                    "script_id": script_id,
                    "stream_id": stream_id,
                    "delta": delta,
                    "kind": "llm_summary",
                    "source": "llm_summary",
                    "visibility": "user",
                    "conversation_id": conversation_id,
                    "agent_name": MASTER_AGENT_NAME,
                }
            )

        on_summary_delta, drain_summary = make_batched_delta_handler(emit_summary_delta)

        plan = self._store.get_plan(script_id)
        summary = await generate_user_summary(
            self._active_llm_client(),
            user_message=user_text,
            script=script,
            plan=plan,
            observations=observations,
            project_id=project_id,
            script_id=script_id,
            conversation_id=conversation_id,
            conversations=self._conversations,
            on_delta=on_summary_delta,
        )

        await drain_summary()
        await self._emitter.emit(
            {
                "type": "llm_stream_end",
                "script_id": script_id,
                "stream_id": stream_id,
                "kind": "llm_summary",
                "source": "llm_summary",
                "visibility": "user",
                "conversation_id": conversation_id,
                "agent_name": MASTER_AGENT_NAME,
            }
        )
        await self._emit_llm_summary(project_id, script_id, conversation_id, summary)
        self._conversation_index.touch_after_message(
            conversation_id, last_summary=summary
        )
        await self._finalize_token_round(conversation_id, project_id, script_id)
        log_stage(
            logger,
            "super_video_master",
            "ReAct 对话驱动结束",
            script_id=script_id,
            status=script.status.value,
            conversation_id=conversation_id,
        )
        log_perf(
            "chat",
            "run_from_message 完成",
            duration_ms=(time.perf_counter() - run_start) * 1000,
            script_id=script_id,
            conversation_id=conversation_id,
            status=script.status.value,
        )
        return conversation_id, summary
