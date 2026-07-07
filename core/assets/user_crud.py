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

_CREATE_ACTION: dict[str, str] = {
    TextAssetType.PLOT.value: "create_plot",
    TextAssetType.CHARACTER.value: "create_character",
    TextAssetType.SCENE.value: "create_scene",
    TextAssetType.PROP.value: "create_prop",
}

_DELETE_ACTION: dict[str, str] = {
    TextAssetType.PLOT.value: "delete_plot",
    TextAssetType.CHARACTER.value: "delete_character",
    TextAssetType.SCENE.value: "delete_scene",
    TextAssetType.PROP.value: "delete_prop",
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
    try:
        at = TextAssetType(asset_type)
    except ValueError as exc:
        raise ValueError(f"不支持的资产类型: {asset_type}") from exc
    action = _CREATE_ACTION.get(at.value)
    if not action:
        raise ValueError(f"类型 {asset_type} 不支持手动创建")

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("名称不能为空")

    if at == TextAssetType.PLOT:
        payload = dict(content or {})
        if "text" not in payload:
            payload["text"] = clean_name
    else:
        incoming = content or {}
        payload = _minimal_image_text_content(
            at,
            name=clean_name,
            summary=str(incoming.get("summary", "")),
            description=str(incoming.get("description", "")),
        )
        payload.update({k: v for k, v in incoming.items() if v is not None})

    asset = create_text_asset_for_action(
        store,
        action=action,
        project_id=project_id,
        script_id=script_id,
        asset_name=clean_name,
        content=payload,
        observation="",
    )
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
            raise ValueError(
                f"资产被 {len(external)} 处引用，无法删除"
            ) from exc

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
