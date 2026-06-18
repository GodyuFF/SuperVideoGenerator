"""Mock 子 Agent：各 Agent 在隔离会话中 ReAct 执行，后续可替换为真实 API。"""

import asyncio
from typing import Any

from core.agents.base import ReActAgent
from core.agents.react_core import AgentRunContext
from core.constants import VIDEO_GEN_COST_PER_SHOT_USD
from core.logging.setup import get_logger, log_stage
from core.models.entities import (
    AssetScope,
    StepOutput,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoPlanShot,
    VideoStyleMode,
)

logger = get_logger("core.agents")


class ScriptAgent(ReActAgent):
    """剧本 Agent：解析任务简报并生成文字资产。"""

    name = "script_agent"
    display_name = "剧本 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["parse_brief", "create_plot", "create_character", "create_scene"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        log_stage(logger, "agent.script", action, step_id=ctx.step_id)
        await asyncio.sleep(0.01)
        script_id = ctx.work_context["script_id"]
        project_id = ctx.work_context["project_id"]

        if action == "parse_brief":
            script = self._store.get_script(script_id)
            if script and not script.content_md:
                script.content_md = f"# {script.title}\n\n基于任务简报生成的剧本内容。"
            return f"已解析任务简报，目标剧本 ID={script_id}。"

        if action == "create_plot":
            plot = TextAsset(
                project_id=project_id,
                script_id=script_id,
                scope=AssetScope.SCRIPT_PRIVATE,
                type=TextAssetType.PLOT,
                name="剧情段落1",
                content={"text": "主角登场，故事开始。"},
            )
            self._store.add_text_asset(plot)
            ctx.outputs.append(StepOutput(kind="json", label="plot", asset_id=plot.id))
            return f"已创建剧情资产 {plot.id}。"

        if action == "create_character":
            character = TextAsset(
                project_id=project_id,
                scope=AssetScope.PROJECT_SHARED,
                type=TextAssetType.CHARACTER,
                name="主角",
                content={"appearance": "年轻女性，短发"},
                source_script_id=script_id,
            )
            self._store.add_text_asset(character)
            ctx.outputs.append(
                StepOutput(kind="json", label="character", asset_id=character.id)
            )
            return f"已创建人物资产 {character.id}。"

        if action == "create_scene":
            scene = TextAsset(
                project_id=project_id,
                scope=AssetScope.PROJECT_SHARED,
                type=TextAssetType.SCENE,
                name="城市街道",
                content={"description": "现代都市黄昏"},
                source_script_id=script_id,
            )
            self._store.add_text_asset(scene)
            ctx.outputs.append(StepOutput(kind="json", label="scene", asset_id=scene.id))
            return f"已创建场景资产 {scene.id}。"

        raise ValueError(f"未知行动: {action}")


class ImageAgent(ReActAgent):
    """图片素材 Agent。"""

    name = "image_agent"
    display_name = "图片 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["scan_text_assets", "generate_images"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        log_stage(logger, "agent.image", action, step_id=ctx.step_id)
        await asyncio.sleep(0.01)
        script_id = ctx.work_context["script_id"]

        if action == "scan_text_assets":
            assets = self._store.list_assets_for_script(script_id)
            visual = [
                a for a in assets
                if a.type in (TextAssetType.CHARACTER, TextAssetType.SCENE)
            ]
            return f"扫描到 {len(visual)} 个待生成图片的文字资产。"

        if action == "generate_images":
            assets = self._store.list_assets_for_script(script_id)
            count = 0
            for asset in assets:
                if asset.type in (TextAssetType.CHARACTER, TextAssetType.SCENE):
                    img_id = f"img_{asset.id.split('_', 1)[-1]}"
                    ctx.outputs.append(
                        StepOutput(
                            kind="image",
                            label=asset.name,
                            asset_id=img_id,
                            url=f"/assets/{img_id}.png",
                        )
                    )
                    count += 1
            return f"已生成 {count} 张图片素材。"

        raise ValueError(f"未知行动: {action}")


class StoryboardAgent(ReActAgent):
    """分镜 Agent。"""

    name = "storyboard_agent"
    display_name = "分镜 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["load_context", "create_shots", "persist_plan"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        log_stage(logger, "agent.storyboard", action, step_id=ctx.step_id)
        await asyncio.sleep(0.01)
        script_id = ctx.work_context["script_id"]
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.DYNAMIC_IMAGE)

        if action == "load_context":
            assets = len(self._store.list_assets_for_script(script_id))
            return f"已加载剧本上下文，关联资产 {assets} 个。"

        if action == "create_shots":
            shots = [
                VideoPlanShot(
                    order=0, duration_ms=3000,
                    narration_text="开场旁白", camera_motion="ken_burns_in",
                ),
                VideoPlanShot(
                    order=1, duration_ms=4000,
                    narration_text="情节发展", camera_motion="pan_right",
                ),
                VideoPlanShot(
                    order=2, duration_ms=3000,
                    narration_text="结尾", camera_motion="fade",
                ),
            ]
            ctx.work_context["_pending_shots"] = shots
            return f"已设计 {len(shots)} 个镜头。"

        if action == "persist_plan":
            shots = ctx.work_context.get("_pending_shots", [])
            vp = VideoPlan(script_id=script_id, mode=style_mode, shots=shots)
            self._store.set_video_plan(vp)
            ctx.outputs.append(StepOutput(kind="json", label="video_plan", asset_id=vp.id))
            return f"视频计划稿已保存，镜头数 {len(shots)}。"

        raise ValueError(f"未知行动: {action}")


class VideoAgent(ReActAgent):
    """视频 Agent（含费用预估观察）。"""

    name = "video_agent"
    display_name = "视频 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["load_shots", "generate_clips"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        log_stage(logger, "agent.video", action, step_id=ctx.step_id)
        await asyncio.sleep(0.02)
        script_id = ctx.work_context["script_id"]

        if action == "load_shots":
            vp = self._store.get_video_plan_for_script(script_id)
            shot_count = len(vp.shots) if vp else 3
            ctx.work_context["_shot_count"] = shot_count
            cost = VIDEO_GEN_COST_PER_SHOT_USD * shot_count
            return f"已加载 {shot_count} 个镜头，预估费用 ${cost:.2f}。"

        if action == "generate_clips":
            shot_count = ctx.work_context.get("_shot_count", 3)
            for i in range(shot_count):
                vid_id = f"vid_{ctx.step_id[-8]}_{i}"
                ctx.outputs.append(
                    StepOutput(
                        kind="video",
                        label=f"shot_{i}",
                        asset_id=vid_id,
                        url=f"/assets/{vid_id}.mp4",
                    )
                )
            return f"已生成 {shot_count} 段视频片段。"

        raise ValueError(f"未知行动: {action}")


class TTSAgent(ReActAgent):
    """TTS Agent。"""

    name = "tts_agent"
    display_name = "配音 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["extract_narration", "synthesize"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        log_stage(logger, "agent.tts", action, step_id=ctx.step_id)
        await asyncio.sleep(0.01)

        if action == "extract_narration":
            script_id = ctx.work_context["script_id"]
            vp = self._store.get_video_plan_for_script(script_id)
            lines = len(vp.shots) if vp else 1
            return f"已提取 {lines} 条旁白文案。"

        if action == "synthesize":
            tts_id = f"tts_{ctx.step_id[-8]}"
            ctx.outputs.append(
                StepOutput(
                    kind="audio",
                    label="narration",
                    asset_id=tts_id,
                    url="/assets/narration.mp3",
                )
            )
            return f"配音已合成，资产 ID={tts_id}。"

        raise ValueError(f"未知行动: {action}")


class EditingAgent(ReActAgent):
    """剪辑 Agent。"""

    name = "editing_agent"
    display_name = "剪辑 Agent"

    def get_action_pipeline(self) -> list[str]:
        return ["gather_media", "compose_final"]

    async def execute_action(self, action: str, ctx: AgentRunContext) -> str:
        log_stage(logger, "agent.editing", action, step_id=ctx.step_id)
        await asyncio.sleep(0.01)

        if action == "gather_media":
            return "已收集图片、视频与配音素材，准备合成。"

        if action == "compose_final":
            fin_id = f"fin_{ctx.step_id[-8]}"
            ctx.outputs.append(
                StepOutput(
                    kind="video",
                    label="final_video",
                    asset_id=fin_id,
                    url=f"/assets/{fin_id}.mp4",
                )
            )
            return f"成片已合成，输出 {fin_id}。"

        raise ValueError(f"未知行动: {action}")
