"""各 tool 的 output JSON Schema（MCP outputSchema）。"""

from __future__ import annotations

from typing import Any


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    additional_properties: bool = True,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        out["required"] = required
    return out


def list_text_assets_output_schema() -> dict[str, Any]:
    linked_media_item = _object_schema(
        {
            "id": {"type": "string"},
            "type": {"type": "string"},
            "name": {"type": "string"},
            "url": {"type": "string"},
            "status": {"type": "string"},
        },
        required=["id", "type", "name", "url", "status"],
        additional_properties=False,
    )
    script_block = _object_schema(
        {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "duration_sec": {"type": "integer"},
            "status": {"type": "string"},
            "content_md": {"type": "string"},
            "style_mode": {"type": ["string", "null"]},
        },
        required=["id", "title", "duration_sec", "status", "content_md", "style_mode"],
        additional_properties=False,
    )
    asset_item = _object_schema(
        {
            "id": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["character", "scene", "prop", "plot"],
            },
            "name": {"type": "string"},
            "scope": {"type": "string"},
            "linked": {"type": "boolean"},
            "content": {"type": "object"},
            "status": {"type": "string"},
            "user_edited": {"type": "boolean"},
            "reuse_policy": {"type": "string"},
            "source_script_id": {"type": ["string", "null"]},
            "relation": {"type": ["string", "null"]},
            "primary_media_id": {"type": ["string", "null"]},
            "traits": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "linked_media": {
                "type": "array",
                "items": linked_media_item,
            },
        },
        required=[
            "id",
            "type",
            "name",
            "scope",
            "linked",
            "content",
            "status",
            "user_edited",
            "reuse_policy",
            "source_script_id",
            "relation",
            "primary_media_id",
        ],
        additional_properties=False,
    )
    return _object_schema(
        {
            "script_id": {"type": "string"},
            "script": {
                "oneOf": [script_block, {"type": "null"}],
            },
            "count": {"type": "integer"},
            "counts_by_type": {
                "type": "object",
                "additionalProperties": {"type": "integer"},
            },
            "assets": {
                "type": "array",
                "items": asset_item,
            },
            "message": {"type": "string"},
        },
        required=["script_id", "script", "count", "counts_by_type", "assets"],
        additional_properties=False,
    )


def asset_mutation_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "asset_id": {"type": "string"},
            "type": {"type": "string"},
            "name": {"type": "string"},
            "scope": {"type": "string"},
            "content": {"type": "object"},
            "merged_fields": {"type": "array", "items": {"type": "string"}},
        },
        required=["asset_id", "type"],
    )


def delete_asset_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "asset_id": {"type": "string"},
            "deleted": {"type": "boolean"},
        },
        required=["asset_id", "deleted"],
    )


def script_mutation_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "script_id": {"type": "string"},
            "title": {"type": "string"},
            "duration_sec": {"type": "integer"},
            "content_md_preview": {"type": "string"},
            "updated_fields": {"type": "array", "items": {"type": "string"}},
        },
        required=["script_id", "updated_fields"],
    )


def plot_content_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "asset_id": {"type": "string"},
            "type": {"type": "string"},
            "content": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        },
        required=["asset_id", "type", "content"],
    )


def read_webpage_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "truncated": {"type": "boolean"},
            "content_length": {"type": "integer"},
            "extraction_method": {"type": "string"},
            "valid": {"type": "boolean"},
        },
        required=["url", "title", "content", "truncated", "valid"],
        additional_properties=False,
    )


def media_list_output_schema() -> dict[str, Any]:
    item = _object_schema(
        {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "type": {"type": "string"},
            "status": {"type": "string"},
            "url": {"type": "string"},
            "link": {"type": "string"},
            "file_path": {"type": "string"},
            "is_accessible": {"type": "boolean"},
            "is_placeholder": {"type": "boolean"},
            "source_asset_id": {"type": ["string", "null"]},
            "source_asset_name": {"type": "string"},
            "source_asset_type": {"type": "string"},
            "generation_prompt_preview": {"type": "string"},
        },
        required=["id", "name", "type", "url"],
        additional_properties=True,
    )
    return _object_schema(
        {
            "script_id": {"type": "string"},
            "media_type": {"type": "string"},
            "count": {"type": "integer"},
            "accessible_count": {"type": "integer"},
            "items": {"type": "array", "items": item},
            "message": {"type": "string"},
        },
        required=["count", "items"],
    )


def read_only_items_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "items": {"type": "array"},
            "count": {"type": "integer"},
            "message": {"type": "string"},
        },
        required=["count"],
    )


def video_plan_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "plan_id": {"type": "string"},
            "mode": {"type": "string"},
            "shot_count": {"type": "integer"},
            "shots": {"type": "array"},
            "message": {"type": "string"},
        },
        required=["shot_count", "shots"],
    )


def load_edit_context_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "action": {"type": "string"},
            "script_id": {"type": "string"},
            "script": {"type": "object"},
            "video_plan": {"type": ["object", "null"]},
            "edit_timeline": {"type": ["object", "null"]},
            "layer_summary": {"type": ["object", "null"]},
            "shot_gaps": {"type": "array"},
            "text_assets": {"type": "array"},
            "media": {"type": "object"},
            "summary": {"type": "object"},
            "plots": {"type": "array"},
            "plot_count": {"type": "integer"},
            "assets_with_images": {"type": "array"},
            "linked_image_count": {"type": "integer"},
            "message": {"type": "string"},
        },
        required=["action", "script_id", "media", "summary"],
        additional_properties=True,
    )


def storyboard_load_context_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "action": {"type": "string"},
            "script_id": {"type": "string"},
            "script": {"type": "object"},
            "count": {"type": "integer"},
            "counts_by_type": {"type": "object"},
            "pending_count": {"type": "integer"},
            "plot_count": {"type": "integer"},
            "plots": {"type": "array"},
            "linked_image_count": {"type": "integer"},
            "assets_with_images": {"type": "array"},
            "assets": {"type": "array"},
            "message": {"type": "string"},
        },
        required=[
            "action",
            "script_id",
            "script",
            "count",
            "assets",
            "plots",
            "linked_image_count",
        ],
        additional_properties=True,
    )


def edit_timeline_board_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "duration_ms": {"type": "integer"},
            "tracks": {"type": "object"},
            "timeline": {"type": ["object", "null"]},
            "message": {"type": "string"},
        },
        required=["duration_ms"],
        additional_properties=True,
    )


def build_edit_timeline_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "timeline": {"type": "object"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "layer_summary": {"type": "object"},
        },
        required=["timeline"],
        additional_properties=True,
    )


def validate_edit_assets_output_schema() -> dict[str, Any]:
    """validate_edit_assets / report_missing_assets 输出 schema。"""
    missing_item = _object_schema(
        {
            "category": {"type": "string"},
            "clip_id": {"type": "string"},
            "track": {"type": "string"},
            "shot_id": {"type": "string"},
            "text_asset_id": {"type": "string"},
            "reason": {"type": "string"},
            "suggested_upstream": {"type": "string"},
        },
        additional_properties=True,
    )
    resolved_clip = _object_schema(
        {
            "clip_id": {"type": "string"},
            "track": {"type": "string"},
            "media_id": {"type": "string"},
            "media_type": {"type": "string"},
            "url": {"type": "string"},
            "link": {"type": "string"},
            "is_accessible": {"type": "boolean"},
        },
        additional_properties=True,
    )
    return _object_schema(
        {
            "ready": {"type": "boolean"},
            "missing_items": {"type": "array", "items": missing_item},
            "resolved_clips": {"type": "array", "items": resolved_clip},
            "summary": {"type": "object"},
        },
        required=["ready", "missing_items", "summary"],
        additional_properties=True,
    )


def scan_text_assets_output_schema() -> dict[str, Any]:
    linked_media_item = _object_schema(
        {
            "id": {"type": "string"},
            "type": {"type": "string"},
            "name": {"type": "string"},
            "url": {"type": "string"},
            "status": {"type": "string"},
            "is_placeholder": {"type": "boolean"},
            "image_status": {
                "type": "string",
                "enum": ["ready", "missing", "placeholder"],
            },
        },
        required=["id", "type", "name", "url", "status", "is_placeholder", "image_status"],
        additional_properties=False,
    )
    script_block = _object_schema(
        {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "duration_sec": {"type": "integer"},
            "status": {"type": "string"},
            "style_mode": {"type": ["string", "null"]},
        },
        required=["id", "title", "duration_sec", "status", "style_mode"],
        additional_properties=False,
    )
    variant_row = _object_schema(
        {
            "id": {"type": "string"},
            "kind": {"type": "string"},
            "label": {"type": "string"},
            "meaning": {"type": "string"},
            "media_id": {"type": ["string", "null"]},
            "reference_variant_id": {"type": "string"},
            "reference_media_id": {"type": ["string", "null"]},
            "reference_ready": {"type": "boolean"},
            "image_status": {"type": "string"},
            "needs_generation": {"type": "boolean"},
            "has_image_prompt": {"type": "boolean"},
            "image_prompt_preview": {"type": "string"},
        },
        additional_properties=True,
    )
    asset_item = _object_schema(
        {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["character", "scene", "prop", "frame"],
            },
            "summary": {"type": "string"},
            "trait_summary": {"type": "string"},
            "linked": {"type": "boolean"},
            "has_image": {"type": "boolean"},
            "image_status": {
                "type": "string",
                "enum": ["ready", "missing", "placeholder"],
            },
            "needs_generation": {"type": "boolean"},
            "source_mode": {"type": "string"},
            "linked_image_id": {"type": ["string", "null"]},
            "variants": {"type": "array", "items": variant_row},
            "pending_variant_count": {"type": "integer"},
            "element_refs": {"type": "object"},
            "variant_refs": {"type": "object"},
            "references_ready": {"type": "boolean"},
            "pending_reason": {"type": "string"},
            "reference_media_ids": {"type": "array", "items": {"type": "string"}},
            "shot_id": {"type": "string"},
            "has_image_prompt": {"type": "boolean"},
            "image_prompt_preview": {"type": "string"},
        },
        required=[
            "id",
            "name",
            "type",
            "summary",
            "trait_summary",
            "linked",
            "has_image",
            "image_status",
            "needs_generation",
            "source_mode",
            "linked_image_id",
            "variants",
            "pending_variant_count",
        ],
        additional_properties=True,
    )
    return _object_schema(
        {
            "project_id": {"type": "string"},
            "project_title": {"type": "string"},
            "script_id": {"type": "string"},
            "script": script_block,
            "count": {"type": "integer"},
            "counts_by_type": {
                "type": "object",
                "additionalProperties": {"type": "integer"},
            },
            "pending_count": {"type": "integer"},
            "source_mode": {"type": "string"},
            "assets": {"type": "array", "items": asset_item},
            "message": {"type": "string"},
        },
        required=[
            "project_id",
            "script_id",
            "script",
            "count",
            "counts_by_type",
            "pending_count",
            "source_mode",
            "assets",
        ],
        additional_properties=False,
    )


def search_images_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "added": {"type": "integer"},
            "results": {"type": "array"},
        },
        required=["added", "results"],
        additional_properties=True,
    )


def sync_text_from_image_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "asset_id": {"type": "string"},
            "skipped": {"type": "boolean"},
            "skip_reason": {"type": "string"},
            "auto_patched": {"type": "array", "items": {"type": "string"}},
            "major_pending": {"type": "array", "items": {"type": "string"}},
            "major_applied": {"type": "array", "items": {"type": "string"}},
        },
        required=["asset_id"],
        additional_properties=True,
    )


def generic_action_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "action": {"type": "string"},
            "summary": {"type": "string"},
        },
        required=["action"],
    )


def storyboard_shots_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "action": {"type": "string"},
            "summary": {"type": "string"},
            "shot_count": {"type": "integer"},
            "output_count": {"type": "integer"},
            "asset_ids": {"type": "array", "items": {"type": "string"}},
        },
        required=["action"],
        additional_properties=True,
    )


def error_output_schema() -> dict[str, Any]:
    return _object_schema(
        {
            "error": {"type": "string"},
            "valid": {"type": "boolean"},
        },
        required=["error", "valid"],
    )
