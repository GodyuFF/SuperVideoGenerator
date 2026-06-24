"""子 Agent 动作执行：通过 LLM 生成观察结果并落盘资产。"""

from typing import Any

from core.agents.react_core import AgentRunContext
from core.constants import VIDEO_GEN_COST_PER_SHOT_USD
from core.llm.client import LLMClient
from core.logging.setup import get_logger, log_stage
from core.agents.tools.executor import AgentToolExecutor
from core.models.entities import (
    AssetReference,
    AssetScope,
    AssetStatus,
    MediaAsset,
    MediaAssetType,
    RelationType,
    StepOutput,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoPlanShot,
    VideoStyleMode,
    new_id,
)
from core.store.memory import MemoryStore
from core.store.persist import schedule_save

logger = get_logger("core.agents.llm_action")

ACTION_JSON_SYSTEM_BASE = """你是视频制作流水线中的专业 Agent，正在执行 ReAct 循环中的单个行动。
根据任务简报、历史观察与当前行动，生成执行结果。

必须且只能返回一个 JSON 对象（不要 Markdown 代码块），至少包含：
{"observation": "给 ReAct 的简短观察（中文）"}

规则：
1. 剧情、人物、场景、旁白必须紧扣任务简报中的「用户创意」，禁止通用模板文案（如「开场旁白」「情节发展」）。
2. create_shots 的 narration_text 须引用当前剧本与文字资产中的具体内容。
3. 未接入真实媒体 API 时，generate_images / generate_clips / synthesize / compose_final 不要编造 url，只返回 observation。

按行动补充字段（示例）：
- parse_brief: script_md（剧本 markdown 字符串）
- create_plot / create_character / create_scene: asset_name, content（对象或字符串）
- scan_text_assets: count（数字）
- generate_images: items（[{asset_id, name, url, source_text_asset_id}]，无真实 API 时可省略 items）
- load_context: asset_count
- create_shots: shots（[{order, duration_ms, narration_text, camera_motion}]，必填且至少 1 镜）
- persist_plan: 无额外字段
- load_shots: shot_count, estimated_cost_usd
- generate_clips: clips（[{label, asset_id, url}]，无真实 API 时可省略 clips）
- extract_narration: line_count
- synthesize: asset_id, url, label（无真实 url 时省略 url）
- gather_media: summary
- compose_final: asset_id, url, label（无真实 url 时省略 url）
"""


def build_action_system_prompt(action_hint: str = "") -> str:
    if not action_hint.strip():
        return ACTION_JSON_SYSTEM_BASE
    return f"{ACTION_JSON_SYSTEM_BASE}\n模式补充：{action_hint.strip()}\n"

_SCRIPT_MD_MAX = 2000
_ASSET_SUMMARY_MAX = 120

_ASSET_CONTENT_KEY: dict[str, str] = {
    "create_plot": "text",
    "create_character": "appearance",
    "create_scene": "description",
}


def _persist_media(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    media_type: MediaAssetType,
    name: str,
    url: str,
    asset_id: str | None = None,
    source_asset_id: str | None = None,
) -> MediaAsset:
    media = MediaAsset(
        id=asset_id or new_id("media"),
        project_id=project_id,
        script_id=script_id,
        type=media_type,
        name=name,
        url=url,
        source_asset_id=source_asset_id,
        status=AssetStatus.GENERATED,
    )
    store.add_media_asset(media)
    if source_asset_id:
        ref = AssetReference(
            source_id=source_asset_id,
            target_id=media.id,
            relation=RelationType.GENERATES,
            script_id=script_id,
        )
        store.add_reference(ref)
    return media


def _is_placeholder_url(url: str) -> bool:
    u = url.strip().lower()
    if not u:
        return True
    if "example.com" in u:
        return True
    if u.startswith("/assets/"):
        return True
    return False


def _coerce_asset_content(action: str, raw: Any, observation: str) -> dict[str, Any]:
    """将 LLM 返回的 content（可能是 str 或 dict）规范为 TextAsset 所需的 dict。"""
    key = _ASSET_CONTENT_KEY.get(action, "text")
    if isinstance(raw, dict) and raw:
        return raw
    if isinstance(raw, str) and raw.strip():
        return {key: raw.strip()}
    if observation.strip():
        return {key: observation.strip()}
    return {key: ""}


def _asset_content_summary(content: dict[str, Any]) -> str:
    for key in ("text", "description", "appearance", "content"):
        val = content.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            if len(text) > _ASSET_SUMMARY_MAX:
                return text[:_ASSET_SUMMARY_MAX] + "…"
            return text
    return ""


def _build_store_context_block(store: MemoryStore, work_context: dict[str, Any]) -> str:
    script_id = str(work_context.get("script_id", ""))
    lines: list[str] = []

    user_message = work_context.get("user_message")
    if user_message:
        lines.append(f"用户创意：{user_message}")

    script = store.get_script(script_id) if script_id else None
    if script and script.content_md.strip():
        md = script.content_md.strip()
        if len(md) > _SCRIPT_MD_MAX:
            md = md[:_SCRIPT_MD_MAX] + "…"
        lines.append(f"当前剧本正文：\n{md}")

    assets = store.list_assets_for_script(script_id) if script_id else []
    if assets:
        lines.append("已有文字资产：")
        for asset in assets:
            summary = _asset_content_summary(asset.content)
            suffix = f" — {summary}" if summary else ""
            lines.append(f"- [{asset.type.value}] {asset.name} ({asset.id}){suffix}")

    media = store.list_media_for_script(script_id) if script_id else []
    if media:
        lines.append("已有媒体资产：")
        for m in media:
            url_part = f" url={m.url}" if m.url else ""
            src = f" src={m.source_asset_id}" if m.source_asset_id else ""
            lines.append(f"- [{m.type.value}] {m.name} ({m.id}){src}{url_part}")

    vp = store.get_video_plan_for_script(script_id) if script_id else None
    if vp and vp.shots:
        lines.append(f"已有分镜：{len(vp.shots)} 镜（persist_plan 前可能为草稿）")
        for shot in sorted(vp.shots, key=lambda s: s.order)[:3]:
            refs = ""
            if shot.asset_refs:
                refs = " refs=" + ",".join(
                    f"{k}:{','.join(v)}" for k, v in shot.asset_refs.items()
                )
            lines.append(
                f"  - 镜{shot.order + 1}: {shot.narration_text[:40]}…{refs}"
            )

    return "\n".join(lines) + ("\n" if lines else "")


def build_action_user_content(
    *,
    store: MemoryStore,
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
    store_block = _build_store_context_block(store, work_context)
    return (
        f"角色：{display_name}\n"
        f"角色说明：{role_prompt}\n"
        f"任务简报：{task_brief}\n"
        f"工作上下文：{ctx_line}\n"
        f"{store_block}"
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
    user_message = str(ctx.work_context.get("user_message", "")).strip()

    if action == "parse_brief":
        script = store.get_script(script_id)
        if script and data.get("script_md"):
            script.content_md = str(data["script_md"])
        elif script and not script.content_md:
            title = script.title or user_message or "未命名剧本"
            body = observation or user_message or "待补充剧情"
            script.content_md = f"# {title}\n\n{body}"
        if not observation:
            observation = f"已解析任务简报，剧本 ID={script_id}。"

    elif action == "create_plot":
        plot = TextAsset(
            project_id=project_id,
            script_id=script_id,
            scope=AssetScope.SCRIPT_PRIVATE,
            type=TextAssetType.PLOT,
            name=str(data.get("asset_name", "剧情段落1")),
            content=_coerce_asset_content(action, data.get("content"), observation),
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
            content=_coerce_asset_content(action, data.get("content"), observation),
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
            content=_coerce_asset_content(action, data.get("content"), observation),
            source_script_id=script_id,
        )
        store.add_text_asset(scene)
        ctx.outputs.append(StepOutput(kind="json", label="scene", asset_id=scene.id))
        if not observation:
            observation = f"已创建场景资产 {scene.id}。"

    elif action == "scan_text_assets":
        summary = AgentToolExecutor.scan_summary(store, script_id)
        if not observation:
            observation = summary

    elif action == "generate_images":
        items = data.get("items")
        added = 0
        if isinstance(items, list) and items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", ""))
                if _is_placeholder_url(url):
                    continue
                media_id = str(item.get("asset_id", new_id("media")))
                name = str(item.get("name", "image"))
                source_id = item.get("source_text_asset_id")
                _persist_media(
                    store,
                    project_id=project_id,
                    script_id=script_id,
                    media_type=MediaAssetType.IMAGE,
                    name=name,
                    url=url,
                    asset_id=media_id,
                    source_asset_id=str(source_id) if source_id else None,
                )
                ctx.outputs.append(
                    StepOutput(
                        kind="image",
                        label=name,
                        asset_id=media_id,
                        url=url,
                    )
                )
                added += 1
        if not observation:
            if added:
                observation = f"已记录 {added} 张图片素材。"
            else:
                observation = "图片生成 API 尚未接入，已跳过媒体 URL 落盘。"

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
                narration = str(raw.get("narration_text", "")).strip()
                if not narration:
                    continue
                refs = raw.get("asset_refs") or {}
                if isinstance(refs, dict):
                    refs = {str(k): [str(v) for v in (val if isinstance(val, list) else [val])] for k, val in refs.items()}
                shots.append(
                    VideoPlanShot(
                        order=int(raw.get("order", i)),
                        duration_ms=int(raw.get("duration_ms", 3000)),
                        narration_text=narration,
                        camera_motion=str(raw.get("camera_motion", "ken_burns_in")),
                        asset_refs=refs if isinstance(refs, dict) else {},
                    )
                )
        if not shots:
            raise ValueError("create_shots 未返回有效镜头列表")
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
        shot_count, cost = AgentToolExecutor.load_shots_summary(store, script_id)
        shot_count = int(data.get("shot_count", shot_count or 3))
        ctx.work_context["_shot_count"] = shot_count
        cost = float(data.get("estimated_cost_usd", VIDEO_GEN_COST_PER_SHOT_USD * shot_count))
        if not observation:
            observation = f"已加载 {shot_count} 个镜头，预估费用 ${cost:.2f}。"

    elif action == "generate_clips":
        clips = data.get("clips")
        added = 0
        if isinstance(clips, list) and clips:
            for i, raw in enumerate(clips):
                if not isinstance(raw, dict):
                    continue
                url = str(raw.get("url", ""))
                if _is_placeholder_url(url):
                    continue
                vid_id = str(raw.get("asset_id", new_id("media")))
                label = str(raw.get("label", f"shot_{i}"))
                _persist_media(
                    store,
                    project_id=project_id,
                    script_id=script_id,
                    media_type=MediaAssetType.VIDEO,
                    name=label,
                    url=url,
                    asset_id=vid_id,
                )
                ctx.outputs.append(
                    StepOutput(
                        kind="video",
                        label=label,
                        asset_id=vid_id,
                        url=url,
                    )
                )
                added += 1
        if not observation:
            if added:
                observation = f"已记录 {added} 段视频片段。"
            else:
                observation = "视频生成 API 尚未接入，已跳过媒体 URL 落盘。"

    elif action == "extract_narration":
        vp = store.get_video_plan_for_script(script_id)
        lines = int(data.get("line_count", len(vp.shots) if vp else 1))
        if not observation:
            observation = f"已提取 {lines} 条旁白文案。"

    elif action == "synthesize":
        url = str(data.get("url", ""))
        if url and not _is_placeholder_url(url):
            tts_id = str(data.get("asset_id", new_id("media")))
            label = str(data.get("label", "narration"))
            _persist_media(
                store,
                project_id=project_id,
                script_id=script_id,
                media_type=MediaAssetType.AUDIO,
                name=label,
                url=url,
                asset_id=tts_id,
            )
            ctx.outputs.append(
                StepOutput(
                    kind="audio",
                    label=label,
                    asset_id=tts_id,
                    url=url,
                )
            )
            if not observation:
                observation = f"配音已合成，资产 ID={tts_id}。"
        elif not observation:
            observation = "TTS API 尚未接入，已跳过音频 URL 落盘。"

    elif action == "gather_media":
        if not observation:
            observation = str(data.get("summary", "已收集图片、视频与配音素材，准备合成。"))

    elif action == "compose_final":
        url = str(data.get("url", ""))
        if url and not _is_placeholder_url(url):
            fin_id = str(data.get("asset_id", new_id("media")))
            label = str(data.get("label", "final_video"))
            _persist_media(
                store,
                project_id=project_id,
                script_id=script_id,
                media_type=MediaAssetType.FINAL,
                name=label,
                url=url,
                asset_id=fin_id,
            )
            ctx.outputs.append(
                StepOutput(
                    kind="video",
                    label=label,
                    asset_id=fin_id,
                    url=url,
                )
            )
            if not observation:
                observation = f"成片已合成，输出 {fin_id}。"
        elif not observation:
            observation = "剪辑合成 API 尚未接入，已跳过成片 URL 落盘。"

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
    system_prompt: str | None = None,
) -> str:
    """调用 LLM 执行单个行动并应用结果。"""
    user_content = build_action_user_content(
        store=store,
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
        system_prompt or build_action_system_prompt(),
        user_content,
        log_context=log_ctx,
        summary_prefix=f"动作 {action}",
    )
    observation = apply_action_result(store, agent_name, action, ctx, data)
    schedule_save(store)
    return observation
