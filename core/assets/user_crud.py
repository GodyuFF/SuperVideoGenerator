"""用户在看板/剧本页手动增删改文字资产与剧本正文。"""

from __future__ import annotations

from typing import Any

from core.assets.service import patch_text_asset
from core.guards.reference import ReferenceGuard, ReferenceGuardError, ScriptEditGuard, ScriptEditGuardError
from core.llm.agent.script_assets import (
    create_text_asset_for_action,
    delete_text_asset_for_action,
)
from core.models.entities import Script, TextAsset, TextAssetType
from core.store.memory import MemoryStore


def _incoming_delete_blockers(
    store: MemoryStore,
    project_id: str,
    script_id: str,
    asset_id: str,
) -> list:
    """汇总阻止删除的谱系入边（排除当前剧本 uses 关联边）。"""
    from core.assets.lineage import build_lineage

    view = build_lineage(store, project_id, asset_id)
    if not view:
        return []
    blockers = []
    for edge in view.incoming:
        if edge.relation == "uses" and edge.source.id == script_id:
            continue
        blockers.append(edge)
    return blockers


def _timeline_media_ids_for_frame(store: MemoryStore, frame_id: str) -> set[str]:
    """列出由 frame 文字资产衍生的媒体 ID。"""
    return {
        m.id
        for m in store.media_assets.values()
        if (m.source_asset_id or "").strip() == frame_id
    }


def _timeline_blocks_frame_media(
    store: MemoryStore, script_id: str, media_ids: set[str]
) -> bool:
    """剪辑时间轴是否仍引用 frame 衍生的媒体。"""
    if not media_ids:
        return False
    timeline = store.get_edit_timeline_for_script(script_id)
    if timeline is None:
        return False
    for layer in timeline.video_layers or []:
        for clip in layer.clips or []:
            if (clip.asset_ref or "") in media_ids:
                return True
    for track_clips in (timeline.tracks or {}).values():
        for clip in track_clips or []:
            if (clip.asset_ref or "") in media_ids:
                return True
    return False


def _purge_media_derived_from_text(store: MemoryStore, text_asset_id: str) -> None:
    """删除文字资产衍生的媒体记录及其引用边。"""
    derived_ids = [
        m.id
        for m in store.media_assets.values()
        if (m.source_asset_id or "").strip() == text_asset_id
    ]
    for mid in derived_ids:
        for ref_id, ref in list(store.references.items()):
            if ref.source_id == mid or ref.target_id == mid:
                store.remove_reference(ref_id)
        if mid in store.media_assets:
            del store.media_assets[mid]


class AssetDeleteBlockedError(Exception):
    """删除被引用资产时携带结构化谱系边。"""

    def __init__(self, asset_id: str, references: list) -> None:
        self.asset_id = asset_id
        self.references = references
        super().__init__(f"资产 {asset_id} 被 {len(references)} 处引用，无法删除")

_CREATE_ACTION: dict[str, str] = {
    TextAssetType.PLOT.value: "create_plot",
    TextAssetType.CHARACTER.value: "create_character",
    TextAssetType.SCENE.value: "create_scene",
    TextAssetType.PROP.value: "create_prop",
    TextAssetType.FRAME.value: "create_frame",
    TextAssetType.VIDEO_CLIP.value: "create_video_clip",
}

MANUAL_CREATABLE_TYPES = frozenset(_CREATE_ACTION.keys())

_DELETE_ACTION: dict[str, str] = {
    TextAssetType.PLOT.value: "delete_plot",
    TextAssetType.CHARACTER.value: "delete_character",
    TextAssetType.SCENE.value: "delete_scene",
    TextAssetType.PROP.value: "delete_prop",
    TextAssetType.FRAME.value: "delete_frame",
    TextAssetType.VIDEO_CLIP.value: "delete_video_clip",
}

_TRAIT_DEFAULTS: dict[str, list[str]] = {
    TextAssetType.CHARACTER.value: [
        "role",
        "personality",
        "age_range",
        "gender",
        "costume",
        "distinctive_features",
        "ethnicity",
        "body_type",
        "height",
        "build",
        "hair_style",
        "hair_color",
        "eye_color",
        "facial_features",
        "default_expression",
        "default_pose",
        "accessories",
    ],
    TextAssetType.SCENE.value: [
        "location",
        "time_of_day",
        "weather",
        "lighting",
        "mood",
        "spatial_layout",
        "architecture_style",
        "key_objects",
        "foreground",
        "background",
        "camera_angle",
        "depth_of_field",
        "color_tone",
    ],
    TextAssetType.PROP.value: [
        "category",
        "material",
        "size_scale",
        "usage",
        "condition",
        "shape",
        "color",
        "texture",
        "brand_style",
        "visual_details",
    ],
}


def _pad_description(text: str, min_len: int = 80) -> str:
    body = text.strip() or "待补充描述。"
    if len(body) >= min_len:
        return body
    return body + "。" + "用户手动创建，细节待补充。" * ((min_len - len(body)) // 10 + 1)


def _minimal_image_text_content(
    asset_type: TextAssetType, *, name: str, summary: str = "", description: str = ""
) -> dict[str, Any]:
    desc = _pad_description(description or summary or name)
    content: dict[str, Any] = {
        "summary": (summary or name).strip(),
        "description": desc,
        "prompt_hint": "未指定",
        "visual_style": "未指定",
        "color_palette": "未指定",
    }
    for key in _TRAIT_DEFAULTS.get(asset_type.value, []):
        content[key] = "未指定"
    return content


def _minimal_frame_content(
    *, name: str, summary: str = "", image_prompt: str = "", notes: str = ""
) -> dict[str, Any]:
    """剧本画面 frame 手动创建时的默认 content（精简五块）。"""
    prompt = _pad_description(image_prompt or summary or name)
    return {
        "summary": (summary or name).strip(),
        "image_prompt": prompt,
        "notes": (notes or "").strip(),
        "element_refs": {},
        "reference_order": ["scene", "character", "prop", "frame"],
        "variant_refs": {},
        "prompt_locked": True,
        "prompt_version": 0,
        "negative_prompt": "",
    }


def _minimal_video_clip_content(
    *, name: str, summary: str = "", video_prompt: str = "", notes: str = ""
) -> dict[str, Any]:
    """video_clip 手动创建时的默认 content（精简五块）。"""
    prompt = _pad_description(video_prompt or summary or name)
    return {
        "summary": (summary or name).strip(),
        "video_prompt": prompt,
        "notes": (notes or "").strip(),
        "video_mode": "auto",
        "camera_motion": "static",
        "element_refs": {},
        "variant_refs": {},
        "media_refs": [],
        "reference_order": ["scene", "character", "prop", "frame", "media"],
        "prompt_locked": True,
        "prompt_version": 0,
    }


def script_ids_for_asset(store: MemoryStore, asset: TextAsset) -> set[str]:
    """收集与资产关联的剧本 ID（用于编辑守卫）。"""
    ids: set[str] = set()
    if asset.source_script_id:
        ids.add(asset.source_script_id)
    if asset.script_id:
        ids.add(asset.script_id)
    for ref in store.references.values():
        if ref.target_id == asset.id and ref.script_id:
            ids.add(ref.script_id)
    return ids


def assert_script_manually_editable(store: MemoryStore, script_id: str) -> Script:
    script = store.get_script(script_id)
    if not script:
        raise ValueError(f"剧本 {script_id} 不存在")
    ScriptEditGuard.assert_editable(script)
    return script


def assert_asset_manually_editable(store: MemoryStore, asset: TextAsset) -> None:
    ids = script_ids_for_asset(store, asset)
    if not ids:
        return
    for sid in ids:
        script = store.get_script(sid)
        if script and not ScriptEditGuard.is_editable(script):
            raise ScriptEditGuardError(
                f"剧本 {sid} 状态为 {script.status}，AI 执行中不可编辑"
            )


def user_create_text_asset(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    asset_type: str,
    name: str,
    content: dict[str, Any] | None = None,
) -> TextAsset:
    assert_script_manually_editable(store, script_id)
    clean_type = str(asset_type).strip().lower()
    try:
        at = TextAssetType(clean_type)
    except ValueError as exc:
        raise ValueError(f"不支持的资产类型: {asset_type}") from exc
    action = _CREATE_ACTION.get(at.value)
    if not action:
        allowed = ", ".join(sorted(MANUAL_CREATABLE_TYPES))
        raise ValueError(
            f"类型 {asset_type} 不支持手动创建（允许: {allowed}）"
        )

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("名称不能为空")

    if at == TextAssetType.PLOT:
        payload = dict(content or {})
        if "text" not in payload:
            payload["text"] = clean_name
    elif at == TextAssetType.FRAME:
        incoming = content or {}
        payload = _minimal_frame_content(
            name=clean_name,
            summary=str(incoming.get("summary", "")),
            image_prompt=str(
                incoming.get("image_prompt") or incoming.get("description") or ""
            ),
            notes=str(incoming.get("notes", "")),
        )
        payload.update({k: v for k, v in incoming.items() if v is not None})
        if not str(payload.get("image_prompt") or "").strip() and str(
            payload.get("description") or ""
        ).strip():
            payload["image_prompt"] = str(payload["description"]).strip()
        payload["prompt_locked"] = True
    elif at == TextAssetType.VIDEO_CLIP:
        incoming = content or {}
        payload = _minimal_video_clip_content(
            name=clean_name,
            summary=str(incoming.get("summary", "")),
            video_prompt=str(
                incoming.get("video_prompt") or incoming.get("description") or ""
            ),
            notes=str(incoming.get("notes", "")),
        )
        payload.update({k: v for k, v in incoming.items() if v is not None})
        payload["prompt_locked"] = True
    else:
        incoming = content or {}
        payload = _minimal_image_text_content(
            at,
            name=clean_name,
            summary=str(incoming.get("summary", "")),
            description=str(incoming.get("description", "")),
        )
        payload.update({k: v for k, v in incoming.items() if v is not None})

    outcome = create_text_asset_for_action(
        store,
        action=action,
        project_id=project_id,
        script_id=script_id,
        asset_name=clean_name,
        content=payload,
        observation="",
    )
    asset = outcome.asset
    asset.user_edited = True
    store.update_text_asset(asset)
    return asset


def user_delete_text_asset(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    asset_id: str,
) -> None:
    assert_script_manually_editable(store, script_id)
    asset = store.get_text_asset(asset_id)
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")
    if asset.project_id != project_id:
        raise ValueError(f"资产 {asset_id} 不属于项目 {project_id}")
    assert_asset_manually_editable(store, asset)

    action = _DELETE_ACTION.get(asset.type.value)
    if not action:
        raise ValueError(f"类型 {asset.type.value} 不支持手动删除")

    guard = ReferenceGuard(store)
    try:
        guard.assert_can_delete(asset_id)
    except ReferenceGuardError as exc:
        external = [r for r in exc.references if r.source_id != script_id]
        if external:
            from core.assets.lineage import build_lineage, references_to_lineage_edges

            view = build_lineage(store, project_id, asset_id)
            edges = view.incoming if view else references_to_lineage_edges(
                store, external, target_id=asset_id
            )
            raise AssetDeleteBlockedError(asset_id, edges) from exc

    lineage_blockers = _incoming_delete_blockers(store, project_id, script_id, asset_id)
    if asset.type == TextAssetType.FRAME:
        derived_media = _timeline_media_ids_for_frame(store, asset_id)
        if _timeline_blocks_frame_media(store, script_id, derived_media):
            from core.assets.lineage import LineageEdge, resolve_descriptor

            center = resolve_descriptor(store, asset_id)
            if center:
                lineage_blockers = [
                    *lineage_blockers,
                    LineageEdge(
                        id=f"e_edit_timeline_{asset_id}",
                        relation="edit_timeline_ref",
                        source=resolve_descriptor(store, script_id) or center,
                        target=center,
                        context={"reason": "剪辑时间轴仍引用该画面衍生的媒体"},
                    ),
                ]
    if lineage_blockers:
        raise AssetDeleteBlockedError(asset_id, lineage_blockers)

    if asset.type in (TextAssetType.FRAME, TextAssetType.VIDEO_CLIP):
        _purge_media_derived_from_text(store, asset_id)

    delete_text_asset_for_action(
        store,
        action=action,
        script_id=script_id,
        asset_id=asset_id,
    )


def user_patch_text_asset(
    store: MemoryStore,
    *,
    project_id: str,
    asset_id: str,
    name: str | None = None,
    content: dict[str, Any] | None = None,
    primary_media_id: str | None = None,
    force_recompose_prompt: bool = False,
    prompt_locked: bool | None = None,
) -> TextAsset:
    asset = store.get_text_asset(asset_id)
    if not asset:
        raise ValueError(f"资产 {asset_id} 不存在")
    if asset.project_id != project_id:
        raise ValueError(f"资产 {asset_id} 不属于项目 {project_id}")
    assert_asset_manually_editable(store, asset)
    from core.models.video_text_asset import is_video_text_asset

    if is_video_text_asset(asset.type.value):
        from core.assets.video_text_service import patch_video_text_asset

        return patch_video_text_asset(
            store,
            project_id=project_id,
            asset_id=asset_id,
            name=name,
            content=content,
            primary_media_id=primary_media_id,
            force_recompose_prompt=force_recompose_prompt,
            prompt_locked=prompt_locked,
        )
    return patch_text_asset(
        store,
        project_id=project_id,
        asset_id=asset_id,
        name=name,
        content=content,
        primary_media_id=primary_media_id,
        force_recompose_prompt=force_recompose_prompt,
        prompt_locked=prompt_locked,
    )


def user_patch_script(
    store: MemoryStore,
    *,
    project_id: str,
    script_id: str,
    title: str | None = None,
    content_md: str | None = None,
    duration_sec: int | None = None,
) -> Script:
    script = assert_script_manually_editable(store, script_id)
    if script.project_id != project_id:
        raise ValueError(f"剧本 {script_id} 不属于项目 {project_id}")
    if title is not None and title.strip():
        script.title = title.strip()
    if content_md is not None:
        script.content_md = content_md
    if duration_sec is not None and duration_sec > 0:
        script.duration_sec = duration_sec
    return script
