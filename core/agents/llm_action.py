"""子 Agent 动作执行：通过 LLM 生成观察结果并落盘资产。"""

from typing import Any

from core.agents.react_core import AgentRunContext
from core.constants import VIDEO_GEN_COST_PER_SHOT_USD
from core.llm.client import LLMClient
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
from core.store.memory import MemoryStore

logger = get_logger("core.agents.llm_action")

ACTION_JSON_SYSTEM = """你是视频制作流水线中的专业 Agent，正在执行 ReAct 循环中的单个行动。
根据任务简报、历史观察与当前行动，生成执行结果。

必须且只能返回一个 JSON 对象（不要 Markdown 代码块），至少包含：
{"observation": "给 ReAct 的简短观察（中文）"}

按行动补充字段（示例）：
- parse_brief: script_md（剧本 markdown 字符串）
- create_plot / create_character / create_scene: asset_name, content（对象）
- scan_text_assets: count（数字）
- generate_images: items（[{asset_id, name, url}]）
- load_context: asset_count
- create_shots: shots（[{order, duration_ms, narration_text, camera_motion}]）
- persist_plan: 无额外字段
- load_shots: shot_count, estimated_cost_usd
- generate_clips: clips（[{label, asset_id, url}]）
- extract_narration: line_count
- synthesize: asset_id, url, label
- gather_media: summary
- compose_final: asset_id, url, label
"""


def build_action_user_content(
    *,
    role_prompt: str,
    display_name: str,
    action: str,
    task_brief: str,
    observations: list[str],
    completed_actions: set[str],
    work_context: dict[str, Any],
) -> str:
    obs = "\n".join(f"- {o}" for o in observations) or "- 无"
    done = ", ".join(sorted(completed_actions)) or "无"
    ctx_parts = []
    for key in ("script_id", "project_id", "style_mode"):
        if key in work_context:
            val = work_context[key]
            if hasattr(val, "value"):
                val = val.value
            ctx_parts.append(f"{key}={val}")
    ctx_line = ", ".join(ctx_parts)
    return (
        f"角色：{display_name}\n"
        f"角色说明：{role_prompt}\n"
        f"任务简报：{task_brief}\n"
        f"工作上下文：{ctx_line}\n"
        f"当前行动：{action}\n"
        f"已完成行动：{done}\n"
        f"历史观察：\n{obs}\n"
    )


def apply_action_result(
    store: MemoryStore,
    agent_name: str,
    action: str,
    ctx: AgentRunContext,
    data: dict[str, Any],
) -> str:
    """将 LLM JSON 结果应用到存储，返回 observation。"""
    observation = str(data.get("observation", "")).strip()
    script_id = ctx.work_context["script_id"]
    project_id = ctx.work_context["project_id"]

    if action == "parse_brief":
        script = store.get_script(script_id)
        if script and data.get("script_md"):
            script.content_md = str(data["script_md"])
        elif script and not script.content_md:
            script.content_md = f"# {script.title}\n\n{observation}"
        if not observation:
            observation = f"已解析任务简报，剧本 ID={script_id}。"

    elif action == "create_plot":
        plot = TextAsset(
            project_id=project_id,
            script_id=script_id,
            scope=AssetScope.SCRIPT_PRIVATE,
            type=TextAssetType.PLOT,
            name=str(data.get("asset_name", "剧情段落1")),
            content=data.get("content") or {"text": observation},
        )
        store.add_text_asset(plot)
        ctx.outputs.append(StepOutput(kind="json", label="plot", asset_id=plot.id))
        if not observation:
            observation = f"已创建剧情资产 {plot.id}。"

    elif action == "create_character":
        character = TextAsset(
            project_id=project_id,
            scope=AssetScope.PROJECT_SHARED,
            type=TextAssetType.CHARACTER,
            name=str(data.get("asset_name", "主角")),
            content=data.get("content") or {"appearance": observation},
            source_script_id=script_id,
        )
        store.add_text_asset(character)
        ctx.outputs.append(
            StepOutput(kind="json", label="character", asset_id=character.id)
        )
        if not observation:
            observation = f"已创建人物资产 {character.id}。"

    elif action == "create_scene":
        scene = TextAsset(
            project_id=project_id,
            scope=AssetScope.PROJECT_SHARED,
            type=TextAssetType.SCENE,
            name=str(data.get("asset_name", "场景")),
            content=data.get("content") or {"description": observation},
            source_script_id=script_id,
        )
        store.add_text_asset(scene)
        ctx.outputs.append(StepOutput(kind="json", label="scene", asset_id=scene.id))
        if not observation:
            observation = f"已创建场景资产 {scene.id}。"

    elif action == "scan_text_assets":
        assets = store.list_assets_for_script(script_id)
        visual = [
            a for a in assets
            if a.type in (TextAssetType.CHARACTER, TextAssetType.SCENE)
        ]
        count = int(data.get("count", len(visual)))
        if not observation:
            observation = f"扫描到 {count} 个待生成图片的文字资产。"

    elif action == "generate_images":
        items = data.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                ctx.outputs.append(
                    StepOutput(
                        kind="image",
                        label=str(item.get("name", "image")),
                        asset_id=str(item.get("asset_id", "img_unknown")),
                        url=str(item.get("url", "")),
                    )
                )
        else:
            assets = store.list_assets_for_script(script_id)
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
        if not observation:
            observation = f"已生成 {len(ctx.outputs)} 张图片素材。"

    elif action == "load_context":
        assets = len(store.list_assets_for_script(script_id))
        count = int(data.get("asset_count", assets))
        if not observation:
            observation = f"已加载剧本上下文，关联资产 {count} 个。"

    elif action == "create_shots":
        shots_data = data.get("shots")
        shots: list[VideoPlanShot] = []
        if isinstance(shots_data, list) and shots_data:
            for i, raw in enumerate(shots_data):
                if not isinstance(raw, dict):
                    continue
                shots.append(
                    VideoPlanShot(
                        order=int(raw.get("order", i)),
                        duration_ms=int(raw.get("duration_ms", 3000)),
                        narration_text=str(raw.get("narration_text", "")),
                        camera_motion=str(raw.get("camera_motion", "ken_burns_in")),
                    )
                )
        if not shots:
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
        if not observation:
            observation = f"已设计 {len(shots)} 个镜头。"

    elif action == "persist_plan":
        shots = ctx.work_context.get("_pending_shots", [])
        style_mode = ctx.work_context.get("style_mode", VideoStyleMode.DYNAMIC_IMAGE)
        vp = VideoPlan(script_id=script_id, mode=style_mode, shots=shots)
        store.set_video_plan(vp)
        ctx.outputs.append(StepOutput(kind="json", label="video_plan", asset_id=vp.id))
        if not observation:
            observation = f"视频计划稿已保存，镜头数 {len(shots)}。"

    elif action == "load_shots":
        vp = store.get_video_plan_for_script(script_id)
        shot_count = int(data.get("shot_count", len(vp.shots) if vp else 3))
        ctx.work_context["_shot_count"] = shot_count
        cost = float(
            data.get("estimated_cost_usd", VIDEO_GEN_COST_PER_SHOT_USD * shot_count)
        )
        if not observation:
            observation = f"已加载 {shot_count} 个镜头，预估费用 ${cost:.2f}。"

    elif action == "generate_clips":
        shot_count = int(ctx.work_context.get("_shot_count", 3))
        clips = data.get("clips")
        if isinstance(clips, list) and clips:
            for i, raw in enumerate(clips):
                if not isinstance(raw, dict):
                    continue
                ctx.outputs.append(
                    StepOutput(
                        kind="video",
                        label=str(raw.get("label", f"shot_{i}")),
                        asset_id=str(raw.get("asset_id", f"vid_{ctx.step_id[-8]}_{i}")),
                        url=str(raw.get("url", "")),
                    )
                )
        else:
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
        if not observation:
            observation = f"已生成 {shot_count} 段视频片段。"

    elif action == "extract_narration":
        vp = store.get_video_plan_for_script(script_id)
        lines = int(data.get("line_count", len(vp.shots) if vp else 1))
        if not observation:
            observation = f"已提取 {lines} 条旁白文案。"

    elif action == "synthesize":
        tts_id = str(data.get("asset_id", f"tts_{ctx.step_id[-8]}"))
        ctx.outputs.append(
            StepOutput(
                kind="audio",
                label=str(data.get("label", "narration")),
                asset_id=tts_id,
                url=str(data.get("url", "/assets/narration.mp3")),
            )
        )
        if not observation:
            observation = f"配音已合成，资产 ID={tts_id}。"

    elif action == "gather_media":
        if not observation:
            observation = str(data.get("summary", "已收集图片、视频与配音素材，准备合成。"))

    elif action == "compose_final":
        fin_id = str(data.get("asset_id", f"fin_{ctx.step_id[-8]}"))
        ctx.outputs.append(
            StepOutput(
                kind="video",
                label=str(data.get("label", "final_video")),
                asset_id=fin_id,
                url=str(data.get("url", f"/assets/{fin_id}.mp4")),
            )
        )
        if not observation:
            observation = f"成片已合成，输出 {fin_id}。"

    else:
        if not observation:
            observation = f"已完成行动 {action}。"

    log_stage(logger, "agent.llm_action", action, agent=agent_name, step_id=ctx.step_id)
    return observation


async def run_llm_action(
    store: MemoryStore,
    llm_client: LLMClient,
    *,
    agent_name: str,
    display_name: str,
    role_prompt: str,
    action: str,
    ctx: AgentRunContext,
) -> str:
    """调用 LLM 执行单个行动并应用结果。"""
    user_content = build_action_user_content(
        role_prompt=role_prompt,
        display_name=display_name,
        action=action,
        task_brief=ctx.task_brief,
        observations=ctx.observations,
        completed_actions=ctx.completed_actions,
        work_context=ctx.work_context,
    )
    log_ctx = {
        "project_id": ctx.work_context.get("project_id", ""),
        "script_id": ctx.script_id,
        "agent_name": agent_name,
        "step_id": ctx.step_id,
        "role": "agent_action",
        "action": action,
    }
    data = await llm_client.complete_json(
        ACTION_JSON_SYSTEM,
        user_content,
        log_context=log_ctx,
        summary_prefix=f"动作 {action}",
    )
    return apply_action_result(store, agent_name, action, ctx, data)
