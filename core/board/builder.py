"""从 MemoryStore 构建各级看板视图（内容驱动，非静态 mock）。"""

from typing import Any

from core.board.models import BoardEdge, BoardNode, BoardView, PipelineStepView
from core.edit.shot_duration import resolve_display_shot_duration_ms
from core.guards.script_style import normalize_style_mode_id
from core.llm.style.video_capability import style_video_modes
from core.models.entities import AssetScope, MediaAssetType, TextAsset, TextAssetType, VideoStyleMode
from core.models.image_text_asset import (
    extract_traits,
    image_text_preview,
    is_image_text_asset,
    normalize_image_text_content,
)
from core.llm.tools.shared.media_list import resolve_media_access
from core.store.memory import MemoryStore

BOARD_KINDS = [
    "overview",
    "knowledge",
    "script_details",
    "project_graph",
    "script",
    "character",
    "scene",
    "prop",
    "frame",
    "video_clip",
    "storyboard",
    "edit",
    "media",
    "pipeline",
]

BOARD_TITLES: dict[str, str] = {
    "overview": "整体看板",
    "knowledge": "图文资产",
    "script_details": "剧本详情",
    "project_graph": "剧本汇总看板",
    "script": "剧本看板",
    "character": "角色看板",
    "scene": "场景看板",
    "prop": "物品看板",
    "frame": "画面看板",
    "video_clip": "视频片段看板",
    "storyboard": "分镜看板",
    "edit": "剪辑看板",
    "media": "媒体看板",
    "pipeline": "生成顺序",
}


def _format_storyboard_time_ms(ms: int) -> str:
    """将毫秒格式化为分镜表格时间码（m:ss.s）。"""
    total_sec = max(0, ms) / 1000.0
    minutes = int(total_sec // 60)
    seconds = total_sec % 60
    return f"{minutes}:{seconds:04.1f}"


def _storyboard_times_need_repair(items: list[dict]) -> bool:
    """检测分镜看板时间是否未累加（多镜共用起点 0 或非单调）。"""
    if len(items) <= 1:
        return False
    sorted_items = sorted(items, key=lambda x: int(x.get("order", 0)))
    starts = [int(it.get("start_ms", 0)) for it in sorted_items]
    if sum(1 for s in starts if s == 0) > 1:
        return True
    for i in range(1, len(starts)):
        if starts[i] <= starts[i - 1]:
            return True
    return False


def _normalize_storyboard_item_times(
    store: MemoryStore,
    items: list[dict],
    shots: list,
    tts_by_shot: dict[str, str],
) -> None:
    """将非单调分镜时间重算为 plan 累加区间，并同步幕/字幕绝对时间。"""
    if not _storyboard_times_need_repair(items):
        return
    shot_by_id = {s.id: s for s in shots}
    cursor = 0
    from core.edit.shot_flatten import effective_shot_duration_ms

    for item in sorted(items, key=lambda x: int(x.get("order", 0))):
        shot = shot_by_id.get(str(item.get("id", "")))
        if shot is not None:
            duration = effective_shot_duration_ms(shot)
        else:
            duration = int(item.get("duration_ms") or 0)
        item["start_ms"] = cursor
        item["end_ms"] = cursor + duration
        item["timeline_source"] = "plan_estimate"
        item["time_label"] = (
            f"{_format_storyboard_time_ms(cursor)} – "
            f"{_format_storyboard_time_ms(cursor + duration)}"
        )
        shot_start = cursor
        for seg in item.get("subtitle_lines") or []:
            seg["absolute_start_ms"] = shot_start + int(seg.get("start_ms", 0))
            seg["absolute_end_ms"] = shot_start + int(seg.get("end_ms", 0))
        cursor += duration


def _storyboard_shot_preview(
    store: MemoryStore,
    shot,
) -> tuple[str, str]:
    """解析分镜「画面」位预览：仅 frame/图片 media，不含 AI 视频。

    无图片时不返回镜头标题作画面名（避免胶片条误显示标题）。
    仅当存在 frame 文字资产但未生图时返回资产名。
    """
    from core.edit.timeline import resolve_shot_image_ref
    from core.models.entities import MediaAssetType

    media_id = resolve_shot_image_ref(store, shot)
    if media_id:
        media = store.media_assets.get(media_id)
        if media and media.type == MediaAssetType.IMAGE and media.url:
            access = resolve_media_access(media.url)
            name = ""
            for sub in shot.sub_shots or []:
                for img in sub.images or []:
                    fid = str(getattr(img, "frame_asset_id", "") or "").strip()
                    if not fid:
                        continue
                    asset = store.text_assets.get(fid)
                    if asset and asset.name:
                        name = asset.name
                        break
                if name:
                    break
            if not name:
                name = (media.name or "").strip() or "画面"
            return access.get("link") or media.url, name
    # 有 frame 文字资产但未生图时，仍展示资产名（无 URL）
    for sub in shot.sub_shots or []:
        for img in sub.images or []:
            fid = str(getattr(img, "frame_asset_id", "") or "").strip()
            if not fid:
                continue
            asset = store.text_assets.get(fid)
            if asset and asset.name:
                return "", asset.name
    return "", ""


def _storyboard_preview_fallback(
    store: MemoryStore,
    shot,
) -> tuple[str, str]:
    """无 frame 图片时的页面预览兼容：返回视频 URL 与 kind=video。"""
    from core.edit.timeline import resolve_shot_video_ref
    from core.models.entities import MediaAssetType

    media_id = resolve_shot_video_ref(store, shot)
    if not media_id:
        return "", ""
    media = store.media_assets.get(media_id)
    if not media or media.type != MediaAssetType.VIDEO or not media.url:
        return "", ""
    access = resolve_media_access(media.url)
    return access.get("link") or media.url, "video"


def _asset_preview(content: dict) -> str:
    preview = image_text_preview(content)
    if preview:
        return preview
    desc = content.get("description")
    if isinstance(desc, str) and desc.strip():
        text = desc.strip()
        return text[:80] + "…" if len(text) > 80 else text
    return ""


def _video_clip_item(
    store: MemoryStore,
    asset: TextAsset,
    *,
    script_id: str | None = None,
) -> dict:
    """组装 video_clip 文字资产看板条目（含生成视频预览与参考关联）。"""
    from core.assets.lineage import build_lineage, lineage_summary_counts
    from core.llm.tools.video.source_urls import video_clip_asset_preview_url
    from core.models.video_text_asset import normalize_video_clip_content

    content = normalize_video_clip_content(asset.content)
    media = _media_for_text(store, asset.id, script_id=script_id)
    videos = [m for m in media if m.get("type") == "video"]
    # preview_url 走与 media[] 相同的可播放链路；preview 仅保留摘要文案，避免前端去重失败重复渲染
    preview_url = ""
    primary_id = str(asset.primary_media_id or "").strip()
    if primary_id:
        for m in videos:
            if str(m.get("id") or "") == primary_id:
                preview_url = str(m.get("url") or "").strip()
                break
    if not preview_url and videos:
        preview_url = str(videos[0].get("url") or "").strip()
    if not preview_url:
        preview_url = video_clip_asset_preview_url(store, asset.id)
    lineage_summary: dict[str, int] = {"incoming_count": 0, "outgoing_count": 0}
    view = build_lineage(store, asset.project_id, asset.id)
    if view:
        lineage_summary = lineage_summary_counts(view)
    summary = str(content.get("summary") or "").strip()
    video_prompt = str(content.get("video_prompt") or "").strip()
    return {
        "id": asset.id,
        "type": asset.type.value,
        "name": asset.name,
        "summary": summary,
        "video_prompt": video_prompt,
        "tags": content.get("tags", []),
        "video_mode": content.get("video_mode", "auto"),
        "duration_sec": content.get("duration_sec"),
        "camera_motion": content.get("camera_motion", ""),
        "element_refs": content.get("element_refs", {}),
        "media_refs": content.get("media_refs", []),
        "content": content,
        "preview": summary or video_prompt[:80],
        "preview_url": preview_url,
        "videos": videos,
        "media": media,
        "primary_media_id": asset.primary_media_id,
        "status": asset.status.value,
        "scope": asset.scope.value,
        "source_script_id": asset.source_script_id,
        "lineage_summary": lineage_summary,
    }


def _image_text_item(
    store: MemoryStore,
    asset: TextAsset,
    *,
    script_id: str | None = None,
) -> dict:
    from core.assets.lineage import build_lineage, lineage_summary_counts
    from core.models.image_text_asset import parse_image_variants

    content = normalize_image_text_content(asset.type, asset.content)
    media = _media_for_text(store, asset.id, script_id=script_id)
    images = [m for m in media if m.get("type") == "image"]
    variant_rows: list[dict] = []
    for v in parse_image_variants(content):
        preview = ""
        if v.media_id:
            for m in images:
                if m.get("id") == v.media_id:
                    preview = str(m.get("url", ""))
                    break
        variant_rows.append(
            {
                "id": v.id,
                "kind": v.kind,
                "label": v.label,
                "meaning": v.meaning,
                "variant_prompt": v.variant_prompt,
                "image_prompt": v.image_prompt,
                "media_id": v.media_id,
                "status": v.status,
                "is_primary": v.kind == "base",
                "preview_url": preview,
            }
        )
    lineage_summary: dict[str, int] = {"incoming_count": 0, "outgoing_count": 0}
    view = build_lineage(store, asset.project_id, asset.id)
    if view:
        lineage_summary = lineage_summary_counts(view)
    # preview 保留摘要文案；preview_url 才是缩略图媒体链路
    preview_url = ""
    primary_id = str(asset.primary_media_id or "").strip()
    if primary_id:
        for m in images:
            if str(m.get("id") or "") == primary_id:
                preview_url = str(m.get("url") or "").strip()
                break
    if not preview_url and images:
        preview_url = str(images[0].get("url") or "").strip()
    return {
        "id": asset.id,
        "type": asset.type.value,
        "name": asset.name,
        "summary": content.get("summary", ""),
        "description": content.get("description", ""),
        "visual_style": content.get("visual_style", ""),
        "tags": content.get("tags", []),
        "display_mode": content.get("display_mode", "static_image"),
        "traits": extract_traits(asset.type, content),
        "content": content,
        "variants": variant_rows,
        "preview": image_text_preview(content) or _asset_preview(content),
        "preview_url": preview_url,
        "images": images,
        "media": media,
        "primary_media_id": asset.primary_media_id,
        "status": asset.status.value,
        "scope": asset.scope.value,
        "source_script_id": asset.source_script_id,
        "reuse_policy": asset.reuse_policy,
        "lineage_summary": lineage_summary,
    }


def _media_for_text(
    store: MemoryStore,
    text_asset_id: str,
    *,
    script_id: str | None = None,
) -> list[dict]:
    """按文字资产 ID 收集关联媒体；script_id 存在时仅返回该剧本下的媒体。"""
    result = []
    for m in store.media_assets.values():
        if m.source_asset_id != text_asset_id or not m.url:
            continue
        if script_id is not None and m.script_id != script_id:
            continue
        access = resolve_media_access(m.url)
        result.append(
            {
                "id": m.id,
                "name": m.name,
                "url": access["link"] or m.url,
                "type": m.type.value,
                "script_id": m.script_id,
            }
        )
    return result


class BoardBuilder:
    """根据仓储快照构建看板。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def build(
        self,
        kind: str,
        project_id: str,
        script_id: str | None = None,
    ) -> BoardView:
        if kind not in BOARD_KINDS:
            raise ValueError(f"未知看板类型: {kind}")
        project = self._store.get_project(project_id)
        if not project:
            raise ValueError("项目不存在")

        builders = {
            "overview": self._overview,
            "knowledge": self._knowledge,
            "script_details": self._script_details_board,
            "project_graph": self._project_graph,
            "script": self._script_board,
            "character": self._character_board,
            "scene": self._scene_board,
            "prop": self._prop_board,
            "frame": self._frame_board,
            "video_clip": self._video_clip_board,
            "storyboard": self._storyboard_board,
            "edit": self._edit_board,
            "media": self._media_board,
            "pipeline": self._pipeline_board,
        }
        return builders[kind](project_id, script_id)

    def _overview(self, project_id: str, script_id: str | None) -> BoardView:
        """项目整体看板：剧本按创建顺序排列并附带 1-based 编号。"""
        scripts = self._store.list_scripts_for_project(project_id)
        items = []
        for index, s in enumerate(scripts, start=1):
            payload = self._script_item_payload(s, is_active=s.id == script_id)
            payload["script_index"] = index
            payload["order"] = index
            items.append(payload)

        return BoardView(
            kind="overview",
            title=BOARD_TITLES["overview"],
            description="项目下所有剧本汇总与生成进度（按创建顺序编号）",
            items=items,
            stats={
                "script_count": len(scripts),
                "total_assets": sum(i["asset_count"] for i in items),
                "total_media": sum(i["media_count"] for i in items),
            },
        )

    def _script_item_payload(
        self,
        script,
        *,
        is_active: bool = False,
        include_full_content: bool = False,
    ) -> dict:
        plan = self._store.get_plan(script.id)
        vp = self._store.get_video_plan_for_script(script.id)
        assets = self._store.list_visible_text_assets_for_script(script.id)
        media = self._store.list_media_for_script(script.id)
        completed = 0
        if plan:
            completed = sum(
                1 for step in plan.steps if step.status.value == "completed"
            )
        content_md = script.content_md or ""
        style_mode_id = (
            normalize_style_mode_id(script.style_mode) if script.style_mode else None
        )
        item = {
            "script_id": script.id,
            "title": script.title,
            "status": script.status.value,
            "style_mode": style_mode_id,
            "video_modes": style_video_modes(style_mode_id) if style_mode_id else [],
            "duration_sec": script.duration_sec,
            "created_at": script.created_at or "",
            "asset_count": len(assets),
            "media_count": len(media),
            "shot_count": len(vp.shots) if vp else 0,
            "plan_steps_completed": completed,
            "plan_steps_total": len(plan.steps) if plan else 0,
            "content_preview": content_md[:120],
            "is_active": is_active,
        }
        if include_full_content:
            item["content_md"] = content_md
        return item

    def _plot_items_for_script(self, script_id: str) -> list[dict]:
        """列出剧本私有剧情（plot）资产，供 script_details 看板展示。"""
        plots = [
            a
            for a in self._store.list_assets_for_script(script_id)
            if a.script_id == script_id and a.type == TextAssetType.PLOT
        ]
        return [
            {
                "id": a.id,
                "type": a.type.value,
                "name": a.name,
                "preview": _asset_preview(a.content),
            }
            for a in sorted(plots, key=lambda x: x.name)
        ]

    def _script_tab_visibility_stats(self, script_id: str) -> dict[str, int | bool]:
        script = self._store.get_script(script_id)
        assets = self._store.list_visible_text_assets_for_script(script_id)
        media = self._store.list_media_for_script(script_id)
        vp = self._store.get_video_plan_for_script(script_id)
        timeline = self._store.get_edit_timeline_for_script(script_id)
        plan = self._store.get_plan(script_id)
        content_md = (script.content_md or "").strip() if script else ""
        character_count = sum(
            1 for a in assets if a.type == TextAssetType.CHARACTER
        )
        scene_count = sum(1 for a in assets if a.type == TextAssetType.SCENE)
        prop_count = sum(1 for a in assets if a.type == TextAssetType.PROP)
        frame_count = sum(1 for a in assets if a.type == TextAssetType.FRAME)
        video_clip_count = sum(1 for a in assets if a.type == TextAssetType.VIDEO_CLIP)
        return {
            "has_content_md": bool(content_md),
            "character_count": character_count,
            "scene_count": scene_count,
            "prop_count": prop_count,
            "frame_count": frame_count,
            "video_clip_count": video_clip_count,
            "shot_count": len(vp.shots) if vp else 0,
            "media_count": len(media),
            "has_edit_timeline": timeline is not None,
            "has_pipeline": plan is not None,
        }

    def _script_details_board(self, project_id: str, script_id: str | None) -> BoardView:
        if not script_id:
            raise ValueError("script_details 需要 script_id")
        script = self._store.get_script(script_id)
        if not script or script.project_id != project_id:
            raise ValueError("剧本不存在")

        item = self._script_item_payload(script, is_active=True, include_full_content=True)
        tab_stats = self._script_tab_visibility_stats(script.id)
        plot_items = self._plot_items_for_script(script.id)
        return BoardView(
            kind="script_details",
            title=BOARD_TITLES["script_details"],
            description=f"剧本「{script.title}」详情与生成进度",
            items=[item, *plot_items],
            stats={
                "script_id": script.id,
                "title": script.title,
                "status": script.status.value,
                "style_mode": item["style_mode"],
                "duration_sec": script.duration_sec,
                "asset_count": item["asset_count"],
                "media_count": item["media_count"],
                "shot_count": item["shot_count"],
                "plan_steps_completed": item["plan_steps_completed"],
                "plan_steps_total": item["plan_steps_total"],
                "content_md": item.get("content_md", ""),
                **tab_stats,
            },
        )

    def _knowledge(self, project_id: str, _script_id: str | None) -> BoardView:
        """构建项目级图文资产看板，附带各剧本引用关系与来源剧本标题。"""
        shared = [
            a
            for a in self._store.text_assets.values()
            if a.project_id == project_id
            and a.scope == AssetScope.PROJECT_SHARED
            and is_image_text_asset(a.type)
        ]
        by_type: dict[str, list] = {}
        for a in shared:
            by_type.setdefault(a.type.value, []).append(a)

        scripts = self._store.list_scripts_for_project(project_id)
        script_meta = [
            {"id": s.id, "title": s.title, "script_index": i}
            for i, s in enumerate(scripts, start=1)
        ]
        title_by_id = {s.id: s.title for s in scripts}
        linked_by_script = {
            s.id: self._store._collect_script_linked_target_ids(s.id) for s in scripts
        }

        items = []
        nodes: list[BoardNode] = []
        for asset in sorted(shared, key=lambda x: (x.type.value, x.name)):
            item = _image_text_item(self._store, asset)
            preview = item["preview"]
            media = item["media"]
            referenced_script_ids = [
                sid
                for sid, linked in linked_by_script.items()
                if asset.id in linked
            ]
            source_sid = asset.source_script_id
            item["referenced_script_ids"] = referenced_script_ids
            item["source_script_title"] = (
                title_by_id.get(source_sid) if source_sid else None
            )
            items.append(item)
            nodes.append(
                BoardNode(
                    id=asset.id,
                    kind=asset.type.value,
                    label=asset.name,
                    subtitle=preview,
                    group="shared_pool",
                    meta={
                        "media_count": len(media),
                        "referenced_script_ids": referenced_script_ids,
                        "source_script_id": source_sid,
                    },
                )
            )

        return BoardView(
            kind="knowledge",
            title=BOARD_TITLES["knowledge"],
            description="项目共享池：角色、物品、场景等图文资产",
            items=items,
            nodes=nodes,
            stats={
                "by_type": {t: len(v) for t, v in by_type.items()},
                "scripts": script_meta,
            },
        )

    def _project_graph(self, project_id: str, script_id: str | None) -> BoardView:
        from core.assets.lineage import build_project_graph

        nodes, edges, stats = build_project_graph(
            self._store, project_id, script_id=script_id
        )
        return BoardView(
            kind="project_graph",
            title=BOARD_TITLES["project_graph"],
            description="项目、剧本与资产关联关系图",
            nodes=nodes,
            edges=edges,
            stats=stats,
        )

    def _script_board(self, project_id: str, script_id: str | None) -> BoardView:
        if not script_id:
            return BoardView(
                kind="script",
                title=BOARD_TITLES["script"],
                description="请选择或创建剧本",
            )
        script = self._store.get_script(script_id)
        if not script or script.project_id != project_id:
            raise ValueError("剧本不存在")

        private = [
            a
            for a in self._store.list_assets_for_script(script_id)
            if a.script_id == script_id
        ]
        refs = {
            r.target_id: r.relation.value
            for r in self._store.list_references_from(script_id)
        }
        shared_linked = [
            a
            for a in self._store.list_assets_for_script(script_id)
            if a.script_id != script_id and a.id in refs
        ]
        all_assets = private + [a for a in shared_linked if a not in private]
        items = [
            {
                "id": a.id,
                "type": a.type.value,
                "name": a.name,
                "preview": _asset_preview(a.content),
                "scope": a.scope.value,
                "relation": refs.get(a.id),
                "source_script_id": a.source_script_id,
            }
            for a in all_assets
        ]

        return BoardView(
            kind="script",
            title=BOARD_TITLES["script"],
            description=f"剧本「{script.title}」正文与私有资产",
            items=items,
            stats={
                "title": script.title,
                "status": script.status.value,
                "content_md": script.content_md,
                "style_mode": normalize_style_mode_id(script.style_mode) if script.style_mode else None,
                "duration_sec": script.duration_sec,
                "linked_asset_count": len(refs),
            },
        )

    def _image_text_board(
        self,
        project_id: str,
        script_id: str | None,
        asset_type: TextAssetType,
        *,
        kind: str,
        title: str,
        description: str,
        stat_key: str,
    ) -> BoardView:
        assets = [
            a
            for a in self._store.text_assets.values()
            if a.project_id == project_id and a.type == asset_type
        ]
        if script_id:
            visible_ids = {
                a.id
                for a in self._store.list_visible_text_assets_for_script(script_id)
            }
            assets = [a for a in assets if a.id in visible_ids]
        items = [
            _image_text_item(self._store, a, script_id=script_id)
            for a in sorted(assets, key=lambda x: x.name)
        ]
        return BoardView(
            kind=kind,
            title=title,
            description=description,
            items=items,
            stats={stat_key: len(items)},
        )

    def _character_board(self, project_id: str, script_id: str | None) -> BoardView:
        return self._image_text_board(
            project_id,
            script_id,
            TextAssetType.CHARACTER,
            kind="character",
            title=BOARD_TITLES["character"],
            description="角色设定与关联图片",
            stat_key="character_count",
        )

    def _scene_board(self, project_id: str, script_id: str | None) -> BoardView:
        return self._image_text_board(
            project_id,
            script_id,
            TextAssetType.SCENE,
            kind="scene",
            title=BOARD_TITLES["scene"],
            description="场景设定与关联图片",
            stat_key="scene_count",
        )

    def _prop_board(self, project_id: str, script_id: str | None) -> BoardView:
        return self._image_text_board(
            project_id,
            script_id,
            TextAssetType.PROP,
            kind="prop",
            title=BOARD_TITLES["prop"],
            description="物品/道具设定与关联图片",
            stat_key="prop_count",
        )

    def _frame_board(self, project_id: str, script_id: str | None) -> BoardView:
        return self._image_text_board(
            project_id,
            script_id,
            TextAssetType.FRAME,
            kind="frame",
            title=BOARD_TITLES["frame"],
            description="分镜画面（多参考图合成）",
            stat_key="frame_count",
        )

    def _video_clip_board(self, project_id: str, script_id: str | None) -> BoardView:
        """构建 video_clip 文字资产看板（生视频描述与成片预览）。"""
        assets = [
            a
            for a in self._store.text_assets.values()
            if a.project_id == project_id and a.type == TextAssetType.VIDEO_CLIP
        ]
        if script_id:
            visible_ids = {
                a.id
                for a in self._store.list_visible_text_assets_for_script(script_id)
            }
            assets = [a for a in assets if a.id in visible_ids]
        items = [
            _video_clip_item(self._store, a, script_id=script_id)
            for a in sorted(assets, key=lambda x: x.name)
        ]
        return BoardView(
            kind="video_clip",
            title=BOARD_TITLES["video_clip"],
            description="视频片段（AI 生视频描述与 mp4 成片）",
            items=items,
            stats={"video_clip_count": len(items)},
        )

    def _storyboard_board(self, project_id: str, script_id: str | None) -> BoardView:
        if not script_id:
            return BoardView(kind="storyboard", title=BOARD_TITLES["storyboard"])
        script = self._store.get_script(script_id)
        if not script or script.project_id != project_id:
            raise ValueError("剧本不存在")
        from core.edit.shot_detail_sync import ensure_storyboard_tts_sync, refresh_shot_tts_durations_if_drifted
        from core.llm.tools.shared.media_list import resolve_media_play_link

        ensure_storyboard_tts_sync(self._store, script_id)
        refresh_shot_tts_durations_if_drifted(self._store, script_id)
        vp = self._store.get_video_plan_for_script(script_id)
        if not vp:
            return BoardView(
                kind="storyboard",
                title=BOARD_TITLES["storyboard"],
                description="尚未生成分镜计划稿",
            )

        detail_revision = vp.detail_revision
        from core.assets.lineage import shot_reference_ids
        from core.edit.edit_capabilities import motion_display_label, resolve_motion
        from core.edit.shot_detail_sync import resolve_effective_camera_motion
        from core.edit.shot_timing import resolve_shot_timings
        from core.edit.timeline import build_tts_by_shot
        from core.llm.tools.shared.media_list import resolve_media_access

        timing_by_shot = {t.shot_id: t for t in resolve_shot_timings(self._store, script_id)}
        tts_by_shot = build_tts_by_shot(self._store, script_id)

        items: list[dict] = []
        for shot in sorted(vp.shots, key=lambda s: s.order):
            refs = shot_reference_ids(shot)
            effective_motion = resolve_effective_camera_motion(shot)
            item: dict = {
                "id": shot.id,
                "order": shot.order,
                "duration_ms": shot.duration_ms,
                "title": shot.title,
                "summary": shot.summary,
                "camera_motion": effective_motion,
                "camera_motion_canonical": resolve_motion(effective_motion),
                "camera_motion_label": motion_display_label(effective_motion),
                "asset_refs": refs,
                "sub_shots": [v.model_dump() for v in shot.sub_shots],
                "video_tracks": [t.model_dump() for t in shot.video_tracks],
                "audio_tracks": [t.model_dump() for t in shot.audio_tracks],
                "review_note": shot.review_note,
                "need_regen": shot.need_regen,
                "regen_reason": shot.regen_reason,
                "sync_policy": shot.sync_policy,
                "lip_sync_required": shot.lip_sync_required,
                "sync_notes": shot.sync_notes,
                "proposed_sync_actions": list(shot.proposed_sync_actions or []),
            }
            timing = timing_by_shot.get(shot.id)
            start_ms = timing.timeline_start_ms if timing else 0
            end_ms = timing.timeline_end_ms if timing else shot.duration_ms
            item["start_ms"] = start_ms
            item["end_ms"] = end_ms
            item["timeline_source"] = timing.timeline_source if timing else "plan_estimate"
            item["time_label"] = (
                f"{_format_storyboard_time_ms(start_ms)} – {_format_storyboard_time_ms(end_ms)}"
            )
            if timing:
                subtitle_dicts = [line.to_dict() for line in timing.subtitle_lines]
                item["subtitle_lines"] = subtitle_dicts
                item["subtitle_line_count"] = len(subtitle_dicts)
                item["subtitle_preview"] = subtitle_dicts[:3]
                if timing.tts_duration_ms:
                    item["tts_duration_ms"] = timing.tts_duration_ms

            tts_ms = int(item.get("tts_duration_ms") or 0)
            display_ms, display_source = resolve_display_shot_duration_ms(shot, tts_ms)
            item["display_duration_ms"] = display_ms
            item["display_duration_source"] = display_source

            preview_url, preview_name = _storyboard_shot_preview(self._store, shot)
            if preview_url:
                item["frame_preview_url"] = preview_url
            if preview_name:
                item["frame_asset_name"] = preview_name
            if not preview_url:
                fb_url, fb_kind = _storyboard_preview_fallback(self._store, shot)
                if fb_url:
                    item["preview_fallback_url"] = fb_url
                    item["preview_fallback_kind"] = fb_kind

            char_names: list[str] = []
            for cid in refs.get("character") or []:
                char = self._store.text_assets.get(str(cid))
                if char and char.name:
                    char_names.append(char.name)
            if char_names:
                item["character_names"] = char_names

            audio_id = tts_by_shot.get(shot.id)
            if audio_id:
                media = self._store.media_assets.get(audio_id)
                if media:
                    access = resolve_media_access(media.url)
                    item["tts_asset_id"] = audio_id
                    play_link = resolve_media_play_link(media)
                    item["tts_audio_url"] = play_link or access.get("link") or media.url
            items.append(item)

        _normalize_storyboard_item_times(self._store, items, vp.shots, tts_by_shot)
        style_mode_id = normalize_style_mode_id(script.style_mode) or VideoStyleMode.STORYBOOK.value

        return BoardView(
            kind="storyboard",
            title=BOARD_TITLES["storyboard"],
            description=f"视频计划稿 · {vp.mode.value}",
            items=items,
            stats={
                "shot_count": len(items),
                "plan_id": vp.id,
                "detail_revision": detail_revision,
                "style_mode": style_mode_id,
                "video_modes": style_video_modes(style_mode_id),
            },
        )

    def _edit_board(self, project_id: str, script_id: str | None) -> BoardView:
        if not script_id:
            return BoardView(kind="edit", title=BOARD_TITLES["edit"])
        script = self._store.get_script(script_id)
        if not script or script.project_id != project_id:
            raise ValueError("剧本不存在")
        timeline = self._store.get_edit_timeline_for_script(script_id)
        if not timeline:
            return BoardView(
                kind="edit",
                title=BOARD_TITLES["edit"],
                description="尚未生成剪辑计划稿（多轨时间轴）",
            )
        from core.edit.timeline import timeline_board_items, timeline_duration_ms

        board = timeline_board_items(self._store, timeline)
        duration = timeline_duration_ms(timeline)
        track_items: list[dict] = []
        for track_name in ("video", "audio", "subtitle"):
            for clip in board["tracks"].get(track_name, []):
                track_items.append({**clip, "track": track_name})
        return BoardView(
            kind="edit",
            title=BOARD_TITLES["edit"],
            description=f"剪辑计划稿 · {duration / 1000:.1f}s",
            items=track_items,
            stats={
                "timeline_id": timeline.id,
                "plan_id": timeline.plan_id,
                "duration_ms": duration,
                "video_clips": len(board["tracks"].get("video", [])),
                "audio_clips": len(board["tracks"].get("audio", [])),
                "subtitle_clips": len(board["tracks"].get("subtitle", [])),
                "tracks": board["tracks"],
            },
        )

    def _media_board(self, project_id: str, script_id: str | None) -> BoardView:
        from core.assets.lineage import build_lineage, lineage_summary_counts
        from core.llm.tools.shared.media_list import build_media_item

        if script_id:
            media_list = self._store.list_media_for_script(script_id)
        else:
            media_list = self._store.list_media_for_project(project_id)

        by_type: dict[str, list] = {}
        items = []
        for m in media_list:
            by_type.setdefault(m.type.value, []).append(m)
            access = resolve_media_access(m.url)
            meta = m.metadata or {}
            enriched = build_media_item(self._store, m)
            lineage_summary = {"incoming_count": 0, "outgoing_count": 0}
            view = build_lineage(self._store, project_id, m.id)
            if view:
                lineage_summary = lineage_summary_counts(view)
            items.append(
                {
                    "id": m.id,
                    "type": m.type.value,
                    "name": m.name,
                    "url": access["link"] or m.url,
                    "source_asset_id": m.source_asset_id,
                    "source_asset_name": enriched.get("source_asset_name"),
                    "source_asset_type": enriched.get("source_asset_type"),
                    "script_id": m.script_id,
                    "status": m.status.value,
                    "shot_id": meta.get("shot_id"),
                    "duration_ms": meta.get("duration_ms"),
                    "narration_text": meta.get("narration_text"),
                    "lineage_summary": lineage_summary,
                }
            )

        return BoardView(
            kind="media",
            title=BOARD_TITLES["media"],
            description="图片、视频、配音与成片",
            items=items,
            stats={t: len(v) for t, v in by_type.items()},
        )

    def _pipeline_board(self, project_id: str, script_id: str | None) -> BoardView:
        if not script_id:
            return BoardView(kind="pipeline", title=BOARD_TITLES["pipeline"])

        script = self._store.get_script(script_id)
        if not script or script.project_id != project_id:
            raise ValueError("剧本不存在")

        style_mode_id = (
            normalize_style_mode_id(script.style_mode)
            or VideoStyleMode.STORYBOOK.value
        )
        plan = self._store.get_plan(script_id)

        pipeline: list[PipelineStepView] = []
        if plan and plan.steps:
            for i, step in enumerate(plan.steps):
                pipeline.append(
                    PipelineStepView(
                        order=i + 1,
                        step_type=step.type,
                        title=step.title,
                        agent=step.agent,
                        status=step.status.value,
                        description=step.description or "",
                    )
                )

        remaining_items: list[dict[str, Any]] = []
        if plan and (plan.runtime_summary or "").strip():
            remaining_items.append(
                {
                    "order": 1,
                    "title": plan.runtime_summary,
                    "kind": "runtime_summary",
                }
            )

        return BoardView(
            kind="pipeline",
            title=BOARD_TITLES["pipeline"],
            description="本对话实际执行顺序（按委派追加），非固定模板",
            pipeline=pipeline,
            items=remaining_items,
            stats={"style_mode": style_mode_id},
        )
