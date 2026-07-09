"""从 MemoryStore 构建各级看板视图（内容驱动，非静态 mock）。"""

from core.board.models import BoardEdge, BoardNode, BoardView, PipelineStepView
from core.models.entities import AssetScope, MediaAssetType, TextAsset, TextAssetType, VideoStyleMode
from core.models.image_text_asset import (
    extract_traits,
    image_text_preview,
    is_image_text_asset,
    normalize_image_text_content,
)
from core.llm.tools.shared.media_list import resolve_media_access
from core.store.memory import MemoryStore
from core.llm.master import STEP_META, pipeline_for_style

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


def _asset_preview(content: dict) -> str:
    preview = image_text_preview(content)
    if preview:
        return preview
    for key in ("text", "description", "appearance", "content"):
        val = content.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            return text[:80] + "…" if len(text) > 80 else text
    return ""


def _image_text_item(store: MemoryStore, asset: TextAsset) -> dict:
    from core.models.image_text_asset import parse_image_variants

    content = normalize_image_text_content(asset.type, asset.content)
    media = _media_for_text(store, asset.id)
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
                "media_id": v.media_id,
                "status": v.status,
                "is_primary": v.kind == "base",
                "preview_url": preview,
            }
        )
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
        "images": images,
        "media": media,
        "primary_media_id": asset.primary_media_id,
        "status": asset.status.value,
        "scope": asset.scope.value,
        "source_script_id": asset.source_script_id,
        "reuse_policy": asset.reuse_policy,
    }


def _media_for_text(store: MemoryStore, text_asset_id: str) -> list[dict]:
    result = []
    for m in store.media_assets.values():
        if m.source_asset_id != text_asset_id or not m.url:
            continue
        access = resolve_media_access(m.url)
        result.append(
            {
                "id": m.id,
                "name": m.name,
                "url": access["link"] or m.url,
                "type": m.type.value,
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
            "storyboard": self._storyboard_board,
            "edit": self._edit_board,
            "media": self._media_board,
            "pipeline": self._pipeline_board,
        }
        return builders[kind](project_id, script_id)

    def _overview(self, project_id: str, script_id: str | None) -> BoardView:
        scripts = sorted(
            self._store.list_scripts_for_project(project_id),
            key=lambda s: s.id,
        )
        items = []
        for s in scripts:
            items.append(
                self._script_item_payload(s, is_active=s.id == script_id)
            )

        return BoardView(
            kind="overview",
            title=BOARD_TITLES["overview"],
            description="项目下所有剧本汇总与生成进度",
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
        assets = self._store.list_assets_for_script(script.id)
        media = self._store.list_media_for_script(script.id)
        completed = 0
        if plan:
            completed = sum(
                1 for step in plan.steps if step.status.value == "completed"
            )
        content_md = script.content_md or ""
        item = {
            "script_id": script.id,
            "title": script.title,
            "status": script.status.value,
            "style_mode": script.style_mode.value if script.style_mode else None,
            "duration_sec": script.duration_sec,
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

    def _script_tab_visibility_stats(self, script_id: str) -> dict[str, int | bool]:
        script = self._store.get_script(script_id)
        assets = self._store.list_assets_for_script(script_id)
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
        return {
            "has_content_md": bool(content_md),
            "character_count": character_count,
            "scene_count": scene_count,
            "prop_count": prop_count,
            "frame_count": frame_count,
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
        return BoardView(
            kind="script_details",
            title=BOARD_TITLES["script_details"],
            description=f"剧本「{script.title}」详情与生成进度",
            items=[item],
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

        items = []
        nodes: list[BoardNode] = []
        for asset in sorted(shared, key=lambda x: (x.type.value, x.name)):
            item = _image_text_item(self._store, asset)
            preview = item["preview"]
            media = item["media"]
            items.append(item)
            nodes.append(
                BoardNode(
                    id=asset.id,
                    kind=asset.type.value,
                    label=asset.name,
                    subtitle=preview,
                    group="shared_pool",
                    meta={"media_count": len(media)},
                )
            )

        return BoardView(
            kind="knowledge",
            title=BOARD_TITLES["knowledge"],
            description="项目共享池：角色、物品、场景等图文资产",
            items=items,
            nodes=nodes,
            stats={t: len(v) for t, v in by_type.items()},
        )

    def _project_graph(self, project_id: str, script_id: str | None) -> BoardView:
        project = self._store.get_project(project_id)
        if not project:
            raise ValueError("项目不存在")

        nodes: list[BoardNode] = [
            BoardNode(
                id=project.id,
                kind="project",
                label=project.title,
                subtitle="项目根节点",
                group="project",
            )
        ]
        edges: list[BoardEdge] = []
        scripts = self._store.list_scripts_for_project(project_id)

        for script in scripts:
            sid = script.id
            nodes.append(
                BoardNode(
                    id=sid,
                    kind="script",
                    label=script.title,
                    subtitle=script.status.value,
                    group="scripts",
                    meta={
                        "style_mode": script.style_mode.value if script.style_mode else None,
                        "active": sid == script_id,
                    },
                )
            )
            edges.append(
                BoardEdge(
                    id=f"e_{project.id}_{sid}",
                    source=project.id,
                    target=sid,
                    relation="contains",
                    label="包含",
                )
            )

            for asset in self._store.list_assets_for_script(sid):
                if asset.type == TextAssetType.PLOT and asset.script_id == sid:
                    nodes.append(
                        BoardNode(
                            id=asset.id,
                            kind="plot",
                            label=asset.name,
                            group=f"script_{sid}",
                        )
                    )
                    edges.append(
                        BoardEdge(
                            id=f"e_{sid}_{asset.id}",
                            source=sid,
                            target=asset.id,
                            relation="has_plot",
                            label="剧情",
                        )
                    )

            vp = self._store.get_video_plan_for_script(sid)
            if vp:
                nodes.append(
                    BoardNode(
                        id=vp.id,
                        kind="video_plan",
                        label=f"计划稿 ({len(vp.shots)}镜)",
                        group=f"script_{sid}",
                    )
                )
                edges.append(
                    BoardEdge(
                        id=f"e_{sid}_{vp.id}",
                        source=sid,
                        target=vp.id,
                        relation="has_plan",
                        label="分镜",
                    )
                )

            for asset in self._store.text_assets.values():
                if (
                    asset.project_id == project_id
                    and asset.scope == AssetScope.PROJECT_SHARED
                    and asset.source_script_id == sid
                ):
                    if not any(n.id == asset.id for n in nodes):
                        nodes.append(
                            BoardNode(
                                id=asset.id,
                                kind=asset.type.value,
                                label=asset.name,
                                group="shared_pool",
                            )
                        )
                    edges.append(
                        BoardEdge(
                            id=f"e_{sid}_{asset.id}",
                            source=sid,
                            target=asset.id,
                            relation="uses",
                            label="引用",
                        )
                    )

            for media in self._store.list_media_for_script(sid):
                if not any(n.id == media.id for n in nodes):
                    nodes.append(
                        BoardNode(
                            id=media.id,
                            kind=media.type.value,
                            label=media.name,
                            group=f"script_{sid}",
                        )
                    )
                edges.append(
                    BoardEdge(
                        id=f"e_{sid}_{media.id}",
                        source=sid,
                        target=media.id,
                        relation="generates",
                        label="产出",
                    )
                )

        return BoardView(
            kind="project_graph",
            title=BOARD_TITLES["project_graph"],
            description="项目、剧本与资产关联关系图",
            nodes=nodes,
            edges=edges,
            stats={"node_count": len(nodes), "edge_count": len(edges)},
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
                "style_mode": script.style_mode.value if script.style_mode else None,
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
            script_asset_ids = {
                a.id for a in self._store.list_assets_for_script(script_id)
            }
            assets = [
                a
                for a in assets
                if a.id in script_asset_ids or a.source_script_id == script_id
            ]
        items = [
            _image_text_item(self._store, a)
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

    def _storyboard_board(self, project_id: str, script_id: str | None) -> BoardView:
        if not script_id:
            return BoardView(kind="storyboard", title=BOARD_TITLES["storyboard"])
        script = self._store.get_script(script_id)
        if not script or script.project_id != project_id:
            raise ValueError("剧本不存在")
        vp = self._store.get_video_plan_for_script(script_id)
        if not vp:
            return BoardView(
                kind="storyboard",
                title=BOARD_TITLES["storyboard"],
                description="尚未生成分镜计划稿",
            )

        items = [
            {
                "id": shot.id,
                "order": shot.order,
                "duration_ms": shot.duration_ms,
                "camera_motion": shot.camera_motion,
                "narration_text": shot.narration_text,
                "asset_refs": shot.asset_refs,
            }
            for shot in sorted(vp.shots, key=lambda s: s.order)
        ]
        from core.edit.shot_timing import resolve_shot_timings
        from core.edit.timeline import build_tts_by_shot
        from core.llm.tools.shared.media_list import resolve_media_access

        timing_by_shot = {t.shot_id: t for t in resolve_shot_timings(self._store, script_id)}
        tts_by_shot = build_tts_by_shot(self._store, script_id)
        for item in items:
            shot_id = str(item["id"])
            timing = timing_by_shot.get(shot_id)
            if timing:
                start_ms = timing.timeline_start_ms
                end_ms = timing.timeline_end_ms
                item["start_ms"] = start_ms
                item["end_ms"] = end_ms
                item["timeline_source"] = timing.timeline_source
                item["time_label"] = (
                    f"{_format_storyboard_time_ms(start_ms)} – {_format_storyboard_time_ms(end_ms)}"
                )
                subtitle_dicts = [line.to_dict() for line in timing.subtitle_lines]
                item["subtitle_lines"] = subtitle_dicts
                item["subtitle_line_count"] = len(subtitle_dicts)
                item["subtitle_preview"] = subtitle_dicts[:3]
                if timing.tts_duration_ms:
                    item["tts_duration_ms"] = timing.tts_duration_ms
            else:
                duration = int(item.get("duration_ms") or 0)
                item["start_ms"] = 0
                item["end_ms"] = duration
                item["timeline_source"] = "plan_estimate"
                item["time_label"] = (
                    f"{_format_storyboard_time_ms(0)} – {_format_storyboard_time_ms(duration)}"
                )

            asset_refs = item.get("asset_refs") or {}
            frame_ids = asset_refs.get("frame") or []
            if frame_ids:
                frame_id = str(frame_ids[0])
                frame_asset = self._store.text_assets.get(frame_id)
                if frame_asset:
                    item["frame_asset_name"] = frame_asset.name
                frame_media = _media_for_text(self._store, frame_id)
                frame_images = [m for m in frame_media if m.get("type") == "image"]
                if frame_images:
                    item["frame_preview_url"] = frame_images[0].get("url", "")
                elif frame_asset and frame_asset.primary_media_id:
                    media = self._store.media_assets.get(frame_asset.primary_media_id)
                    if media and media.url:
                        access = resolve_media_access(media.url)
                        item["frame_preview_url"] = access.get("link") or media.url

            char_ids = asset_refs.get("character") or []
            char_names: list[str] = []
            for cid in char_ids:
                char = self._store.text_assets.get(str(cid))
                if char and char.name:
                    char_names.append(char.name)
            if char_names:
                item["character_names"] = char_names

            audio_id = tts_by_shot.get(shot_id)
            if not audio_id:
                continue
            media = self._store.media_assets.get(audio_id)
            if not media:
                continue
            access = resolve_media_access(media.url)
            item["tts_asset_id"] = audio_id
            item["tts_audio_url"] = access.get("link") or media.url
            meta = media.metadata or {}
            if meta.get("duration_ms"):
                item["tts_duration_ms"] = meta["duration_ms"]

        return BoardView(
            kind="storyboard",
            title=BOARD_TITLES["storyboard"],
            description=f"视频计划稿 · {vp.mode.value}",
            items=items,
            stats={"shot_count": len(items), "plan_id": vp.id},
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
            items.append(
                {
                    "id": m.id,
                    "type": m.type.value,
                    "name": m.name,
                    "url": access["link"] or m.url,
                    "source_asset_id": m.source_asset_id,
                    "script_id": m.script_id,
                    "status": m.status.value,
                    "shot_id": meta.get("shot_id"),
                    "duration_ms": meta.get("duration_ms"),
                    "narration_text": meta.get("narration_text"),
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

        style = script.style_mode or VideoStyleMode.DYNAMIC_IMAGE
        delegate_actions = pipeline_for_style(style)
        plan = self._store.get_plan(script_id)
        status_by_type: dict[str, str] = {}
        if plan:
            for step in plan.steps:
                status_by_type[step.type] = step.status.value

        pipeline: list[PipelineStepView] = []
        for i, action in enumerate(delegate_actions):
            step_type = action.replace("delegate_", "").replace("_", "_")
            # map delegate action to step type key in STEP_META
            from core.llm.master import ACTION_TO_STEP

            st = ACTION_TO_STEP.get(action, "")
            meta = STEP_META.get(st, {})
            pipeline.append(
                PipelineStepView(
                    order=i + 1,
                    step_type=st or action,
                    title=meta.get("title", action),
                    agent=meta.get("agent", ""),
                    status=status_by_type.get(st, "pending"),
                    description=meta.get("description", ""),
                )
            )

        script_agent_steps = [
            PipelineStepView(
                order=i + 1,
                step_type=a,
                title=a,
                agent="script_agent",
                status="completed" if plan and status_by_type.get("script_design") == "completed" else "pending",
                description="剧本 Agent 内部行动",
            )
            for i, a in enumerate(
                ["parse_brief", "create_plot", "create_character", "create_scene", "create_prop"]
            )
        ]

        return BoardView(
            kind="pipeline",
            title=BOARD_TITLES["pipeline"],
            description="主编排与子 Agent 固定生成顺序",
            pipeline=pipeline,
            items=[s.model_dump() for s in script_agent_steps],
            stats={"style_mode": style.value},
        )
