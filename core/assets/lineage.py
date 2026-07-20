"""资产谱系查询：合并 references、分镜 asset_refs、frame element_refs、媒体溯源。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.board.models import BoardEdge, BoardNode
from core.guards.script_style import normalize_style_mode_id
from core.models.entities import (
    AssetReference,
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    RelationType,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlan,
    Shot,
    new_id,
)
from core.models.image_text_asset import ImageTextAssetType, normalize_image_text_content
from core.models.video_text_asset import normalize_video_clip_content
from core.store.memory import MemoryStore


def _get_media(store: MemoryStore, media_id: str) -> MediaAsset | None:
    """按 ID 获取媒体资产。"""
    return store.get_media_asset(media_id)

_RELATION_LABELS: dict[str, str] = {
    "uses": "引用",
    "generates": "生成",
    "derived_from": "派生",
    "rag_reuse": "RAG 复用",
    "voice_of": "音色绑定",
    "shot_ref": "分镜引用",
    "element_ref": "画面合成",
    "contains": "包含",
    "has_plan": "分镜计划",
    "has_plot": "剧情",
}


class AssetKind(str, Enum):
    """统一资产类型标识，供谱系查询与关系图使用。"""

    PROJECT = "project"
    SCRIPT = "script"
    VIDEO_PLAN = "video_plan"
    SHOT = "shot"
    TEXT_PLOT = "plot"
    TEXT_CHARACTER = "character"
    TEXT_SCENE = "scene"
    TEXT_PROP = "prop"
    TEXT_FRAME = "frame"
    TEXT_VIDEO_CLIP = "video_clip"
    TEXT_NARRATION = "narration"
    MEDIA_IMAGE = "image"
    MEDIA_AUDIO = "audio"
    MEDIA_VIDEO = "video"
    MEDIA_FINAL = "final"


class AssetDescriptor(BaseModel):
    """资产在谱系图中的统一描述。"""

    id: str
    kind: AssetKind
    name: str
    project_id: str
    script_id: str | None = None
    storage: str = ""
    status: str | None = None


class LineageEdge(BaseModel):
    """一条有向关联边（source → target）。"""

    id: str
    relation: str
    source: AssetDescriptor
    target: AssetDescriptor
    context: dict[str, Any] = Field(default_factory=dict)


class AssetLineageView(BaseModel):
    """单资产完整谱系视图。"""

    asset: AssetDescriptor
    outgoing: list[LineageEdge] = Field(default_factory=list)
    incoming: list[LineageEdge] = Field(default_factory=list)


def lineage_summary_counts(view: AssetLineageView) -> dict[str, int]:
    """返回轻量 incoming/outgoing 计数，供看板 item 摘要。"""
    return {
        "incoming_count": len(view.incoming),
        "outgoing_count": len(view.outgoing),
    }


def _text_kind(asset_type: TextAssetType) -> AssetKind:
    mapping = {
        TextAssetType.PLOT: AssetKind.TEXT_PLOT,
        TextAssetType.CHARACTER: AssetKind.TEXT_CHARACTER,
        TextAssetType.SCENE: AssetKind.TEXT_SCENE,
        TextAssetType.PROP: AssetKind.TEXT_PROP,
        TextAssetType.FRAME: AssetKind.TEXT_FRAME,
        TextAssetType.VIDEO_CLIP: AssetKind.TEXT_VIDEO_CLIP,
        TextAssetType.NARRATION: AssetKind.TEXT_NARRATION,
    }
    return mapping.get(asset_type, AssetKind.TEXT_PLOT)


def _media_kind(media_type: MediaAssetType) -> AssetKind:
    mapping = {
        MediaAssetType.IMAGE: AssetKind.MEDIA_IMAGE,
        MediaAssetType.AUDIO: AssetKind.MEDIA_AUDIO,
        MediaAssetType.VIDEO: AssetKind.MEDIA_VIDEO,
        MediaAssetType.FINAL: AssetKind.MEDIA_FINAL,
    }
    return mapping.get(media_type, AssetKind.MEDIA_IMAGE)


def _descriptor_from_text(asset: TextAsset) -> AssetDescriptor:
    return AssetDescriptor(
        id=asset.id,
        kind=_text_kind(asset.type),
        name=asset.name,
        project_id=asset.project_id,
        script_id=asset.script_id or asset.source_script_id,
        storage="text_assets",
        status=asset.status.value if hasattr(asset.status, "value") else str(asset.status),
    )


def _descriptor_from_media(media: MediaAsset) -> AssetDescriptor:
    return AssetDescriptor(
        id=media.id,
        kind=_media_kind(media.type),
        name=media.name,
        project_id=media.project_id,
        script_id=media.script_id,
        storage="media_assets",
        status=media.status.value if hasattr(media.status, "value") else str(media.status),
    )


def _descriptor_from_script(script: Script) -> AssetDescriptor:
    return AssetDescriptor(
        id=script.id,
        kind=AssetKind.SCRIPT,
        name=script.title,
        project_id=script.project_id,
        script_id=script.id,
        storage="scripts",
        status=script.status.value if hasattr(script.status, "value") else str(script.status),
    )


def _descriptor_from_project(project: Project) -> AssetDescriptor:
    return AssetDescriptor(
        id=project.id,
        kind=AssetKind.PROJECT,
        name=project.title,
        project_id=project.id,
        script_id=None,
        storage="projects",
        status=None,
    )


def shot_reference_ids(shot: Shot) -> dict[str, list[str]]:
    """汇总镜内引用的资产 ID：画面元素引用 + 画面图片 frame/媒体 + 各 clip media。"""
    refs: dict[str, list[str]] = {}

    def _add(key: str, value: str) -> None:
        value = str(value or "").strip()
        if value:
            refs.setdefault(key, [])
            if value not in refs[key]:
                refs[key].append(value)

    for visual in shot.sub_shots:
        for key, ids in (visual.element_refs or {}).items():
            for rid in ids if isinstance(ids, list) else []:
                _add(key, rid)
        for img in visual.images:
            _add("frame", img.frame_asset_id)
            _add("image", img.media_id)
            for mid in img.source_media_ids:
                _add("image", mid)
        for vid in visual.videos:
            _add("video", vid.media_id)
            _add("video_clip", vid.video_clip_asset_id)
            _add("frame", vid.source_frame_asset_id)
    for track in shot.video_tracks:
        for clip in track.clips:
            _add("image", clip.media_id)
    for track in shot.audio_tracks:
        for clip in track.clips:
            _add("audio", clip.media_id)
    return refs


def _shot_label_text(shot: Shot) -> str:
    """取镜头首个 voice 文案或首个画面描述作为标签。"""
    for track in shot.audio_tracks:
        for clip in track.clips:
            if clip.text.strip():
                return clip.text.strip()
    if shot.sub_shots and shot.sub_shots[0].description:
        return shot.sub_shots[0].description.strip()
    return (shot.summary or shot.title or "").strip()


def _descriptor_from_shot(
    shot: Shot,
    *,
    plan: VideoPlan,
    script_id: str,
) -> AssetDescriptor:
    label = f"镜 {shot.order + 1}"
    narration = _shot_label_text(shot)
    if narration:
        label = f"{label}: {narration[:24]}"
    return AssetDescriptor(
        id=shot.id,
        kind=AssetKind.SHOT,
        name=label,
        project_id=plan.script_id and _script_project_id_placeholder(plan, script_id) or "",
        script_id=script_id,
        storage="video_plan",
        status=None,
    )


def _script_project_id_placeholder(plan: VideoPlan, script_id: str) -> str:
    """shot 描述符需要 project_id；由调用方在 resolve 时补全。"""
    return ""


def _descriptor_from_video_plan(plan: VideoPlan, script: Script) -> AssetDescriptor:
    return AssetDescriptor(
        id=plan.id,
        kind=AssetKind.VIDEO_PLAN,
        name=f"计划稿 ({len(plan.shots)}镜)",
        project_id=script.project_id,
        script_id=script.id,
        storage="video_plan",
        status=None,
    )


def _make_edge(
    *,
    relation: str,
    source: AssetDescriptor,
    target: AssetDescriptor,
    context: dict[str, Any] | None = None,
    edge_id: str | None = None,
) -> LineageEdge:
    return LineageEdge(
        id=edge_id or new_id("edge"),
        relation=relation,
        source=source,
        target=target,
        context=dict(context or {}),
    )


def _dedupe_edges(edges: list[LineageEdge]) -> list[LineageEdge]:
    seen: set[tuple[str, str, str]] = set()
    out: list[LineageEdge] = []
    for edge in edges:
        key = (edge.source.id, edge.target.id, edge.relation)
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def resolve_descriptor(store: MemoryStore, asset_id: str) -> AssetDescriptor | None:
    """按 ID 在 text/media/script/project/plan/shot 中定位资产描述符。"""
    text = store.get_text_asset(asset_id)
    if text:
        return _descriptor_from_text(text)

    media = _get_media(store, asset_id)
    if media:
        return _descriptor_from_media(media)

    script = store.get_script(asset_id)
    if script:
        return _descriptor_from_script(script)

    project = store.get_project(asset_id)
    if project:
        return _descriptor_from_project(project)

    for script_obj in store.scripts.values():
        plan = store.get_video_plan_for_script(script_obj.id)
        if plan and plan.id == asset_id:
            return _descriptor_from_video_plan(plan, script_obj)
        if plan:
            for shot in plan.shots:
                if shot.id == asset_id:
                    desc = _descriptor_from_shot(shot, plan=plan, script_id=script_obj.id)
                    desc.project_id = script_obj.project_id
                    return desc

    return None


def _descriptor_for_id(store: MemoryStore, asset_id: str) -> AssetDescriptor | None:
    """解析任意 ID；未知时返回最小占位描述符。"""
    desc = resolve_descriptor(store, asset_id)
    if desc:
        return desc
    return AssetDescriptor(
        id=asset_id,
        kind=AssetKind.TEXT_PLOT,
        name=asset_id,
        project_id="",
        script_id=None,
        storage="unknown",
        status=None,
    )


def _edges_from_references(
    store: MemoryStore,
    asset_id: str,
    center: AssetDescriptor,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """从 store.references 收集 outgoing / incoming 边。"""
    outgoing: list[LineageEdge] = []
    incoming: list[LineageEdge] = []

    for ref in store.list_references_from(asset_id):
        target = _descriptor_for_id(store, ref.target_id)
        if not target.project_id and center.project_id:
            target.project_id = center.project_id
        rel = ref.relation.value if hasattr(ref.relation, "value") else str(ref.relation)
        outgoing.append(
            _make_edge(
                relation=rel,
                source=center,
                target=target,
                context={"script_id": ref.script_id, "ref_id": ref.id},
                edge_id=ref.id,
            )
        )

    for ref in store.list_references_to(asset_id):
        source = _descriptor_for_id(store, ref.source_id)
        if not source.project_id and center.project_id:
            source.project_id = center.project_id
        rel = ref.relation.value if hasattr(ref.relation, "value") else str(ref.relation)
        incoming.append(
            _make_edge(
                relation=rel,
                source=source,
                target=center,
                context={"script_id": ref.script_id, "ref_id": ref.id},
                edge_id=ref.id,
            )
        )

    return outgoing, incoming


def _edges_from_media_source(
    store: MemoryStore,
    asset_id: str,
    center: AssetDescriptor,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """媒体 source_asset_id 与文字资产 generates 关系。"""
    outgoing: list[LineageEdge] = []
    incoming: list[LineageEdge] = []

    if center.storage == "text_assets":
        for media in store.media_assets.values():
            if media.source_asset_id == asset_id:
                target = _descriptor_from_media(media)
                outgoing.append(
                    _make_edge(
                        relation=RelationType.GENERATES.value,
                        source=center,
                        target=target,
                        context={"media_type": media.type.value},
                    )
                )

    if center.storage == "media_assets":
        media = _get_media(store, asset_id)
        if media and media.source_asset_id:
            source = _descriptor_for_id(store, media.source_asset_id)
            if source.id != asset_id:
                incoming.append(
                    _make_edge(
                        relation=RelationType.GENERATES.value,
                        source=source,
                        target=center,
                        context={"media_type": media.type.value},
                    )
                )

    return outgoing, incoming


def _edges_from_shot_refs(
    store: MemoryStore,
    asset_id: str,
    center: AssetDescriptor,
    project_id: str,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """分镜镜内引用（shot_reference_ids）正向与反向。"""
    outgoing: list[LineageEdge] = []
    incoming: list[LineageEdge] = []

    scripts = [
        s for s in store.list_scripts_for_project(project_id)
    ] if project_id else list(store.scripts.values())

    for script in scripts:
        plan = store.get_video_plan_for_script(script.id)
        if not plan:
            continue
        plan_desc = _descriptor_from_video_plan(plan, script)

        for shot in plan.shots:
            shot_desc = _descriptor_from_shot(shot, plan=plan, script_id=script.id)
            shot_desc.project_id = script.project_id

            refs = shot_reference_ids(shot)
            for ref_key, ref_ids in refs.items():
                if not isinstance(ref_ids, list):
                    continue
                for rid in ref_ids:
                    rid = str(rid).strip()
                    if not rid:
                        continue
                    if rid == asset_id:
                        incoming.append(
                            _make_edge(
                                relation="shot_ref",
                                source=shot_desc,
                                target=center,
                                context={
                                    "ref_key": ref_key,
                                    "shot_order": shot.order,
                                    "script_id": script.id,
                                    "script_title": script.title,
                                },
                            )
                        )
                    elif center.kind == AssetKind.SHOT and center.id == shot.id:
                        target = _descriptor_for_id(store, rid)
                        if target.project_id != script.project_id:
                            target.project_id = script.project_id
                        outgoing.append(
                            _make_edge(
                                relation="shot_ref",
                                source=center,
                                target=target,
                                context={"ref_key": ref_key, "shot_order": shot.order},
                            )
                        )

            if center.kind == AssetKind.VIDEO_PLAN and center.id == plan.id:
                outgoing.append(
                    _make_edge(
                        relation="contains",
                        source=center,
                        target=shot_desc,
                        context={"shot_order": shot.order},
                    )
                )
            elif center.kind == AssetKind.SHOT and center.id == shot.id:
                incoming.append(
                    _make_edge(
                        relation="contains",
                        source=plan_desc,
                        target=center,
                        context={"script_id": script.id},
                    )
                )

    return outgoing, incoming


def _edges_from_frame_elements(
    store: MemoryStore,
    asset_id: str,
    center: AssetDescriptor,
    project_id: str,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """frame.content.element_refs 正向与反向。"""
    outgoing: list[LineageEdge] = []
    incoming: list[LineageEdge] = []

    for asset in store.text_assets.values():
        if project_id and asset.project_id != project_id:
            continue
        if asset.type != TextAssetType.FRAME:
            continue
        content = normalize_image_text_content(asset.type, asset.content)
        element_refs = content.get("element_refs")
        if not isinstance(element_refs, dict):
            continue
        frame_desc = _descriptor_from_text(asset)

        for ref_key, ref_ids in element_refs.items():
            if not isinstance(ref_ids, list):
                continue
            for rid in ref_ids:
                rid = str(rid).strip()
                if not rid:
                    continue
                if rid == asset_id:
                    incoming.append(
                        _make_edge(
                            relation="element_ref",
                            source=frame_desc,
                            target=center,
                            context={"ref_key": ref_key, "frame_name": asset.name},
                        )
                    )
                elif center.kind == AssetKind.TEXT_FRAME and center.id == asset.id:
                    target = _descriptor_for_id(store, rid)
                    if project_id:
                        target.project_id = project_id
                    outgoing.append(
                        _make_edge(
                            relation="element_ref",
                            source=center,
                            target=target,
                            context={"ref_key": ref_key},
                        )
                    )

    return outgoing, incoming


def _edges_from_video_clip_elements(
    store: MemoryStore,
    asset_id: str,
    center: AssetDescriptor,
    project_id: str,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """video_clip content 的 element_refs 与 media_refs 正向与反向边。"""
    outgoing: list[LineageEdge] = []
    incoming: list[LineageEdge] = []

    for asset in store.text_assets.values():
        if project_id and asset.project_id != project_id:
            continue
        if asset.type != TextAssetType.VIDEO_CLIP:
            continue
        content = normalize_video_clip_content(asset.content)
        clip_desc = _descriptor_from_text(asset)

        element_refs = content.get("element_refs") or {}
        if isinstance(element_refs, dict):
            for ref_key, ref_ids in element_refs.items():
                if not isinstance(ref_ids, list):
                    continue
                for rid in ref_ids:
                    rid = str(rid).strip()
                    if not rid:
                        continue
                    if rid == asset_id:
                        incoming.append(
                            _make_edge(
                                relation="element_ref",
                                source=clip_desc,
                                target=center,
                                context={"ref_key": ref_key, "video_clip_name": asset.name},
                            )
                        )
                    elif center.kind == AssetKind.TEXT_VIDEO_CLIP and center.id == asset.id:
                        target = _descriptor_for_id(store, rid)
                        if project_id:
                            target.project_id = project_id
                        outgoing.append(
                            _make_edge(
                                relation="element_ref",
                                source=center,
                                target=target,
                                context={"ref_key": ref_key},
                            )
                        )

        for mid in content.get("media_refs") or []:
            mid = str(mid).strip()
            if not mid:
                continue
            if mid == asset_id:
                incoming.append(
                    _make_edge(
                        relation="uses",
                        source=clip_desc,
                        target=center,
                        context={"via": "media_refs"},
                    )
                )
            elif center.kind == AssetKind.TEXT_VIDEO_CLIP and center.id == asset.id:
                target = _descriptor_for_id(store, mid)
                if project_id:
                    target.project_id = project_id
                outgoing.append(
                    _make_edge(
                        relation="uses",
                        source=center,
                        target=target,
                        context={"via": "media_refs"},
                    )
                )

        if center.kind == AssetKind.MEDIA_VIDEO and asset.primary_media_id == asset_id:
            incoming.append(
                _make_edge(
                    relation="generates",
                    source=clip_desc,
                    target=center,
                    context={},
                )
            )
        elif center.kind == AssetKind.TEXT_VIDEO_CLIP and center.id == asset.id and asset.primary_media_id:
            target = _descriptor_for_id(store, asset.primary_media_id)
            if target.id:
                outgoing.append(
                    _make_edge(
                        relation="generates",
                        source=center,
                        target=target,
                        context={},
                    )
                )

    return outgoing, incoming


def _edges_from_media_shot_metadata(
    store: MemoryStore,
    asset_id: str,
    center: AssetDescriptor,
) -> tuple[list[LineageEdge], list[LineageEdge]]:
    """媒体 metadata.shot_id 与分镜的关联。"""
    incoming: list[LineageEdge] = []
    outgoing: list[LineageEdge] = []

    if center.storage != "media_assets":
        return outgoing, incoming

    media = _get_media(store, asset_id)
    if not media:
        return outgoing, incoming

    shot_id = str((media.metadata or {}).get("shot_id", "")).strip()
    if not shot_id:
        return outgoing, incoming

    shot_desc = resolve_descriptor(store, shot_id)
    if shot_desc:
        incoming.append(
            _make_edge(
                relation="shot_ref",
                source=shot_desc,
                target=center,
                context={"via": "media_metadata"},
            )
        )

    return outgoing, incoming


def build_lineage(
    store: MemoryStore,
    project_id: str,
    asset_id: str,
) -> AssetLineageView | None:
    """合并多源引用，构建单资产完整谱系视图。"""
    center = resolve_descriptor(store, asset_id)
    if center is None:
        return None
    if not center.project_id:
        center.project_id = project_id

    outgoing: list[LineageEdge] = []
    incoming: list[LineageEdge] = []

    for collector in (
        lambda: _edges_from_references(store, asset_id, center),
        lambda: _edges_from_media_source(store, asset_id, center),
        lambda: _edges_from_shot_refs(store, asset_id, center, project_id),
        lambda: _edges_from_frame_elements(store, asset_id, center, project_id),
        lambda: _edges_from_video_clip_elements(store, asset_id, center, project_id),
        lambda: _edges_from_media_shot_metadata(store, asset_id, center),
    ):
        out_part, in_part = collector()
        outgoing.extend(out_part)
        incoming.extend(in_part)

    return AssetLineageView(
        asset=center,
        outgoing=_dedupe_edges(outgoing),
        incoming=_dedupe_edges(incoming),
    )


def references_to_lineage_edges(
    store: MemoryStore,
    references: list[AssetReference],
    *,
    target_id: str,
) -> list[LineageEdge]:
    """将 ReferenceGuard 返回的引用边转为 LineageEdge 列表（用于 DELETE 错误响应）。"""
    target = resolve_descriptor(store, target_id)
    if not target:
        target = AssetDescriptor(
            id=target_id,
            kind=AssetKind.TEXT_PLOT,
            name=target_id,
            project_id="",
            storage="unknown",
        )
    edges: list[LineageEdge] = []
    for ref in references:
        source = _descriptor_for_id(store, ref.source_id)
        rel = ref.relation.value if hasattr(ref.relation, "value") else str(ref.relation)
        edges.append(
            _make_edge(
                relation=rel,
                source=source,
                target=target,
                context={"script_id": ref.script_id, "ref_id": ref.id},
                edge_id=ref.id,
            )
        )
    return edges


def build_project_graph(
    store: MemoryStore,
    project_id: str,
    script_id: str | None = None,
) -> tuple[list[BoardNode], list[BoardEdge], dict[str, Any]]:
    """构建项目级关系子图，供看板 project_graph 与独立 graph API 使用。"""
    project = store.get_project(project_id)
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
    node_ids: set[str] = {project.id}

    def _ensure_node(node: BoardNode) -> None:
        if node.id in node_ids:
            return
        nodes.append(node)
        node_ids.add(node.id)

    scripts = store.list_scripts_for_project(project_id)
    if script_id:
        scripts = [s for s in scripts if s.id == script_id] or scripts

    for script in scripts:
        sid = script.id
        _ensure_node(
            BoardNode(
                id=sid,
                kind="script",
                label=script.title,
                subtitle=script.status.value,
                group="scripts",
                meta={
                    "style_mode": normalize_style_mode_id(script.style_mode) if script.style_mode else None,
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

        for asset in store.list_assets_for_script(sid):
            if asset.type == TextAssetType.PLOT and asset.script_id == sid:
                _ensure_node(
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

        vp = store.get_video_plan_for_script(sid)
        if vp:
            _ensure_node(
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
            for shot in vp.shots:
                shot_label = f"镜 {shot.order + 1}"
                _ensure_node(
                    BoardNode(
                        id=shot.id,
                        kind="shot",
                        label=shot_label,
                        group=f"script_{sid}",
                        meta={"order": shot.order},
                    )
                )
                edges.append(
                    BoardEdge(
                        id=f"e_{vp.id}_{shot.id}",
                        source=vp.id,
                        target=shot.id,
                        relation="contains",
                        label="镜头",
                    )
                )
                for ref_key, ref_ids in shot_reference_ids(shot).items():
                    if not isinstance(ref_ids, list):
                        continue
                    for rid in ref_ids:
                        rid = str(rid).strip()
                        if not rid:
                            continue
                        desc = resolve_descriptor(store, rid)
                        if not desc:
                            continue
                        kind = desc.kind.value
                        group = (
                            "shared_pool"
                            if desc.storage == "text_assets"
                            and store.get_text_asset(rid)
                            and store.get_text_asset(rid).scope == AssetScope.PROJECT_SHARED
                            else f"script_{sid}"
                        )
                        _ensure_node(
                            BoardNode(
                                id=rid,
                                kind=kind,
                                label=desc.name,
                                group=group,
                            )
                        )
                        edges.append(
                            BoardEdge(
                                id=f"e_{shot.id}_{rid}_{ref_key}",
                                source=shot.id,
                                target=rid,
                                relation="shot_ref",
                                label=ref_key,
                            )
                        )

        for ref in store.references.values():
            if ref.script_id != sid and ref.source_id != sid:
                continue
            if ref.relation == RelationType.USES and ref.source_id == sid:
                target = store.get_text_asset(ref.target_id)
                if target and target.scope == AssetScope.PROJECT_SHARED:
                    _ensure_node(
                        BoardNode(
                            id=target.id,
                            kind=target.type.value,
                            label=target.name,
                            group="shared_pool",
                        )
                    )
                    edges.append(
                        BoardEdge(
                            id=f"e_{sid}_{target.id}_uses",
                            source=sid,
                            target=target.id,
                            relation="uses",
                            label="引用",
                        )
                    )

        for asset in store.text_assets.values():
            if asset.project_id != project_id or asset.type != TextAssetType.FRAME:
                continue
            if asset.source_script_id != sid and not any(
                ref.target_id == asset.id and ref.script_id == sid
                for ref in store.references.values()
            ):
                continue
            content = normalize_image_text_content(asset.type, asset.content)
            element_refs = content.get("element_refs") or {}
            _ensure_node(
                BoardNode(
                    id=asset.id,
                    kind="frame",
                    label=asset.name,
                    group=f"script_{sid}",
                )
            )
            for ref_key, ref_ids in element_refs.items():
                if not isinstance(ref_ids, list):
                    continue
                for rid in ref_ids:
                    rid = str(rid).strip()
                    if not rid:
                        continue
                    desc = resolve_descriptor(store, rid)
                    if not desc:
                        continue
                    _ensure_node(
                        BoardNode(
                            id=rid,
                            kind=desc.kind.value,
                            label=desc.name,
                            group="shared_pool" if ref_key in ("character", "scene", "prop") else f"script_{sid}",
                        )
                    )
                    edges.append(
                        BoardEdge(
                            id=f"e_{asset.id}_{rid}_{ref_key}",
                            source=asset.id,
                            target=rid,
                            relation="element_ref",
                            label=ref_key,
                        )
                    )

        for asset in store.text_assets.values():
            if asset.project_id != project_id or asset.type != TextAssetType.VIDEO_CLIP:
                continue
            if asset.source_script_id != sid and not any(
                ref.target_id == asset.id and ref.script_id == sid
                for ref in store.references.values()
            ):
                continue
            content = normalize_video_clip_content(asset.content)
            element_refs = content.get("element_refs") or {}
            _ensure_node(
                BoardNode(
                    id=asset.id,
                    kind="video_clip",
                    label=asset.name,
                    group=f"script_{sid}",
                )
            )
            for ref_key, ref_ids in element_refs.items():
                if not isinstance(ref_ids, list):
                    continue
                for rid in ref_ids:
                    rid = str(rid).strip()
                    if not rid:
                        continue
                    desc = resolve_descriptor(store, rid)
                    if not desc:
                        continue
                    _ensure_node(
                        BoardNode(
                            id=rid,
                            kind=desc.kind.value,
                            label=desc.name,
                            group="shared_pool" if ref_key in ("character", "scene", "prop") else f"script_{sid}",
                        )
                    )
                    edges.append(
                        BoardEdge(
                            id=f"e_{asset.id}_{rid}_{ref_key}",
                            source=asset.id,
                            target=rid,
                            relation="element_ref",
                            label=ref_key,
                        )
                    )
            for mid in content.get("media_refs") or []:
                mid = str(mid).strip()
                if not mid:
                    continue
                desc = resolve_descriptor(store, mid)
                if not desc:
                    continue
                _ensure_node(
                    BoardNode(
                        id=mid,
                        kind=desc.kind.value,
                        label=desc.name,
                        group=f"script_{sid}",
                    )
                )
                edges.append(
                    BoardEdge(
                        id=f"e_{asset.id}_{mid}_media",
                        source=asset.id,
                        target=mid,
                        relation="uses",
                        label="media_ref",
                    )
                )
            if asset.primary_media_id:
                pm = store.get_media_asset(asset.primary_media_id)
                if pm:
                    _ensure_node(
                        BoardNode(
                            id=pm.id,
                            kind=pm.type.value,
                            label=pm.name,
                            group=f"script_{sid}",
                        )
                    )
                    edges.append(
                        BoardEdge(
                            id=f"e_{asset.id}_{pm.id}_generates",
                            source=asset.id,
                            target=pm.id,
                            relation="generates",
                            label="生成",
                        )
                    )

        for media in store.list_media_for_script(sid):
            _ensure_node(
                BoardNode(
                    id=media.id,
                    kind=media.type.value,
                    label=media.name,
                    group=f"script_{sid}",
                )
            )
            if media.source_asset_id:
                src = store.get_text_asset(media.source_asset_id)
                if src:
                    _ensure_node(
                        BoardNode(
                            id=src.id,
                            kind=src.type.value,
                            label=src.name,
                            group="shared_pool" if src.scope == AssetScope.PROJECT_SHARED else f"script_{sid}",
                        )
                    )
                    edges.append(
                        BoardEdge(
                            id=f"e_{src.id}_{media.id}_gen",
                            source=src.id,
                            target=media.id,
                            relation="generates",
                            label="生成",
                        )
                    )
                else:
                    edges.append(
                        BoardEdge(
                            id=f"e_{sid}_{media.id}_gen",
                            source=sid,
                            target=media.id,
                            relation="generates",
                            label="产出",
                        )
                    )
            else:
                edges.append(
                    BoardEdge(
                        id=f"e_{sid}_{media.id}_gen",
                        source=sid,
                        target=media.id,
                        relation="generates",
                        label="产出",
                    )
                )

    stats = {"node_count": len(nodes), "edge_count": len(edges)}
    return nodes, edges, stats
