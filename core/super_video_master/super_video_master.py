"""超级视频大师主 Agent：ReAct 编排，与用户及子 Agent 对话隔离。"""

from core.a2ui.manager import ConfirmationManager
from core.agents.conversation import ConversationRole, ConversationStore
from core.super_video_master import MASTER_AGENT_NAME
from core.super_video_master.master_react import MasterReActEngine
from core.events.emitter import EventEmitter
from core.interaction_log.recorder import InteractionRecorder
from core.logging.setup import get_logger, log_stage
from core.dialogue.session_store import DialogueSessionStore
from core.guards.script_style import bind_script_style
from core.llm.client import LLMClient
from core.llm.react_decider import LLMReActDecider
from core.llm.settings import LLMConfigManager
from core.models.entities import ScriptStatus, VideoStyleMode
from core.agents.config_manager import AgentConfigManager
from core.agents.registry import AgentRegistry
from core.store.memory import MemoryStore

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
    ) -> None:
        self._store = store
        self._emitter = emitter
        self._confirmation = confirmation_manager
        self._conversations = conversations or ConversationStore()
        self._dialogue_sessions = DialogueSessionStore()
        self._llm_config = llm_config or LLMConfigManager()
        self._recorder = interaction_recorder
        llm_client = LLMClient(self._llm_config, self._recorder)
        self._llm_client = llm_client
        self._llm_decider = LLMReActDecider(
            self._llm_config, llm_client, self._recorder
        )
        self._agent_config = agent_config or AgentConfigManager()
        self._registry = AgentRegistry(
            store,
            emitter,
            self._conversations,
            self._llm_decider,
            self._recorder,
            self._agent_config,
        )
        self._react = MasterReActEngine(
            store,
            emitter,
            self._registry,
            self._conversations,
            confirmation_manager,
            self._llm_decider,
        )

    async def _emit_llm_summary(self, script_id: str, content: str) -> None:
        self._conversations.add(
            script_id, "master", ConversationRole.MASTER, content
        )
        await self._emitter.emit(
            {
                "type": "master_message",
                "script_id": script_id,
                "role": "super_video_master",
                "agent_name": MASTER_AGENT_NAME,
                "content": content,
                "source": "llm_summary",
            }
        )

    async def run_from_message(
        self,
        project_id: str,
        script_id: str,
        message: str,
        requested_style: VideoStyleMode | None = None,
    ) -> str:
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

        user_text = message.strip()

        # 意图判断：仅视频相关意图进入 ReAct 工具调用流程
        video_keywords = [
            "视频", "剧本", "分镜", "配音", "剪辑", "生成", "制作",
            "ai", "动态图片", "成片", "旁白", "短片", "影片", "故事", "创意", "费用",
        ]
        if not any(k in user_text.lower() for k in video_keywords):
            self._conversations.add(
                script_id, "master", ConversationRole.MASTER, "抱歉，我只能处理视频生成相关的请求。请描述您的视频创意。"
            )
            return "intent-skip", "抱歉，我只能处理视频生成相关的请求。"

        # 信息完整性检查：项目/剧本已具备风格与时长上下文时跳过 A2UI 追问
        style_known = (
            requested_style is not None
            or script.style_locked
            or project.config.style.mode is not None
        )
        has_duration_context = bool(script.duration_sec) or any(
            kw in user_text.lower() for kw in ["秒", "时长", "分钟"]
        )
        needs_clarification = not (style_known and has_duration_context)

        if needs_clarification:
            try:
                req_response = await self._confirmation.request_script_requirements(
                    script_id=script_id,
                    initial_message=user_text,
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
                self._conversations.add(
                    script_id, "master", ConversationRole.MASTER, "已取消剧本生成。"
                )
                return "cancelled", "已取消。"

        style_mode = bind_script_style(script, project, requested_style)
        await self._emitter.emit(
            {
                "type": "script_style_locked",
                "script_id": script_id,
                "style_mode": style_mode.value,
            }
        )
        log_stage(
            logger,
            "super_video_master",
            "剧本视频风格已绑定",
            script_id=script_id,
            style_mode=style_mode.value,
        )

        self._conversations.add(
            script_id, "master", ConversationRole.USER, user_text
        )

        preview = user_text.replace("\n", " ")
        if len(preview) > 48:
            preview = preview[:48] + "…"
        script.title = preview or script.title

        log_stage(logger, "super_video_master", "ReAct 对话驱动开始", script_id=script_id)
        conversation_id = self._dialogue_sessions.create(
            project_id, script_id, user_text
        )

        observations = await self._react.run(
            project_id=project_id,
            script_id=script_id,
            user_message=user_text,
            style_mode=style_mode,
            generation_mode=project.config.generation.mode,
            conversation_id=conversation_id,
        )

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

        async def on_summary_delta(delta: str) -> None:
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

        plan = self._store.get_plan(script_id)
        summary = await generate_user_summary(
            self._llm_client,
            user_message=user_text,
            script=script,
            plan=plan,
            observations=observations,
            project_id=project_id,
            script_id=script_id,
            on_delta=on_summary_delta,
        )

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
        await self._emit_llm_summary(script_id, summary)
        log_stage(
            logger,
            "super_video_master",
            "ReAct 对话驱动结束",
            script_id=script_id,
            status=script.status.value,
            conversation_id=conversation_id,
        )
        return conversation_id, summary
