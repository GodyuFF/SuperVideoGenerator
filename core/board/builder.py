"""从 MemoryStore 构建各级看板视图（内容驱动，非静态 mock）。"""

from core.board.models import BoardEdge, BoardNode, BoardView, PipelineStepView
from core.models.entities import AssetScope, MediaAssetType, TextAssetType, VideoStyleMode
from core.store.memory import MemoryStore
from core.super_video_master.actions import STEP_META, pipeline_for_style

BOARD_KINDS = [
    "overview",
    "knowledge",
    "project_graph",
    "script",
    "character",
    "scene",
    "storyboard",
    "media",
    "pipeline",
]

BOARD_TITLES: dict[str, str] = {
    "overview": "整体看板",
    "knowledge": "知识看板",
    "project_graph": "剧本汇总看板",
    "script": "剧本看板",
    "character": "角色看板",
    "scene": "场景看板",
    "storyboard": "分镜看板",
    "media": "媒体看板",
    "pipeline": "生成顺序",
}


def _asset_preview(content: dict) -> str:
    for key in ("text", "description", "appearance", "content"):
        val = content.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            return text[:80] + "…" if len(text) > 80 else text
    return ""


def _media_for_text(store: MemoryStore, text_asset_id: str) -> list[dict]:
    return [
        {"id": m.id, "name": m.name, "url": m.url, "type": m.type.value}
        for m in store.media_assets.values()
        if m.source_asset_id == text_asset_id and m.url
    ]


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
            "project_graph": self._project_graph,
            "script": self._script_board,
            "character": self._character_board,
            "scene": self._scene_board,
            "storyboard": self._storyboard_board,
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
            plan = self._store.get_plan(s.id)
            vp = self._store.get_video_plan_for_script(s.id)
            assets = self._store.list_assets_for_script(s.id)
            media = self._store.list_media_for_script(s.id)
            completed = 0
            if plan:
                completed = sum(
                    1 for step in plan.steps if step.status.value == "completed"
                )
            items.append(
                {
                    "script_id": s.id,
                    "title": s.title,
                    "status": s.status.value,
                    "style_mode": s.style_mode.value if s.style_mode else None,
                    "duration_sec": s.duration_sec,
                    "asset_count": len(assets),
                    "media_count": len(media),
                    "shot_count": len(vp.shots) if vp else 0,
                    "plan_steps_completed": completed,
                    "plan_steps_total": len(plan.steps) if plan else 0,
                    "content_preview": (s.content_md or "")[:120],
                    "is_active": s.id == script_id,
                }
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

    def _knowledge(self, project_id: str, _script_id: str | None) -> BoardView:
        shared = [
            a
            for a in self._store.text_assets.values()
            if a.project_id == project_id and a.scope == AssetScope.PROJECT_SHARED
        ]
        by_type: dict[str, list] = {}
        for a in shared:
            by_type.setdefault(a.type.value, []).append(a)

        items = []
        nodes: list[BoardNode] = []
        for asset in sorted(shared, key=lambda x: (x.type.value, x.name)):
            preview = _asset_preview(asset.content)
            media = _media_for_text(self._store, asset.id)
            items.append(
                {
                    "id": asset.id,
                    "type": asset.type.value,
                    "name": asset.name,
                    "preview": preview,
                    "source_script_id": asset.source_script_id,
                    "media": media,
                    "status": asset.status.value,
                }
            )
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
            description="项目共享池：人物、道具、场景等可复用知识",
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

    def _character_board(self, project_id: str, script_id: str | None) -> BoardView:
        chars = [
            a
            for a in self._store.text_assets.values()
            if a.project_id == project_id and a.type == TextAssetType.CHARACTER
        ]
        if script_id:
            script_asset_ids = {a.id for a in self._store.list_assets_for_script(script_id)}
            chars = [c for c in chars if c.id in script_asset_ids or c.source_script_id == script_id]

        items = []
        for c in sorted(chars, key=lambda x: x.name):
            media = _media_for_text(self._store, c.id)
            items.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "appearance": _asset_preview(c.content),
                    "content": c.content,
                    "source_script_id": c.source_script_id,
                    "images": [m for m in media if m.get("type") == "image"],
                    "scope": c.scope.value,
                }
            )

        return BoardView(
            kind="character",
            title=BOARD_TITLES["character"],
            description="角色设定与关联图片",
            items=items,
            stats={"character_count": len(items)},
        )

    def _scene_board(self, project_id: str, script_id: str | None) -> BoardView:
        scenes = [
            a
            for a in self._store.text_assets.values()
            if a.project_id == project_id and a.type == TextAssetType.SCENE
        ]
        if script_id:
            script_asset_ids = {a.id for a in self._store.list_assets_for_script(script_id)}
            scenes = [s for s in scenes if s.id in script_asset_ids or s.source_script_id == script_id]

        items = []
        for s in sorted(scenes, key=lambda x: x.name):
            media = _media_for_text(self._store, s.id)
            items.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "description": _asset_preview(s.content),
                    "content": s.content,
                    "images": [m for m in media if m.get("type") == "image"],
                    "source_script_id": s.source_script_id,
                }
            )

        return BoardView(
            kind="scene",
            title=BOARD_TITLES["scene"],
            description="场景设定与关联图片",
            items=items,
            stats={"scene_count": len(items)},
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

        return BoardView(
            kind="storyboard",
            title=BOARD_TITLES["storyboard"],
            description=f"视频计划稿 · {vp.mode.value}",
            items=items,
            stats={"shot_count": len(items), "plan_id": vp.id},
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
            items.append(
                {
                    "id": m.id,
                    "type": m.type.value,
                    "name": m.name,
                    "url": m.url,
                    "source_asset_id": m.source_asset_id,
                    "script_id": m.script_id,
                    "status": m.status.value,
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
            from core.super_video_master.actions import ACTION_TO_STEP

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
                ["parse_brief", "create_plot", "create_character", "create_scene"]
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
