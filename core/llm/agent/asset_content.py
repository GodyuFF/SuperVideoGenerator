"""文字资产 content 字段规范化（LLM 常返回字符串或非标结构）。"""

from typing import Any

from core.models.entities import TextAssetType
from core.models.image_text_asset import (
    is_image_text_asset,
    normalize_image_text_content,
)
from core.models.video_text_asset import normalize_video_clip_content

_ACTION_CONTENT_KEY: dict[str, str] = {
    "create_plot": "text",
    "update_plot": "text",
    "create_character": "description",
    "update_character": "description",
    "create_scene": "description",
    "update_scene": "description",
    "create_prop": "description",
    "update_prop": "description",
    "create_frame": "image_prompt",
    "create_video_clip": "video_prompt",
}

_TYPE_CONTENT_KEY: dict[str, str] = {
    TextAssetType.PLOT.value: "text",
    TextAssetType.CHARACTER.value: "description",
    TextAssetType.SCENE.value: "description",
    TextAssetType.NARRATION.value: "text",
    TextAssetType.PROP.value: "description",
    TextAssetType.FRAME.value: "image_prompt",
    TextAssetType.VIDEO_CLIP.value: "video_prompt",
}

_IMAGE_TEXT_ACTIONS = frozenset(
    {
        "create_character",
        "update_character",
        "create_scene",
        "update_scene",
        "create_prop",
        "update_prop",
        "create_frame",
    }
)

_VIDEO_CLIP_ACTIONS = frozenset({"create_video_clip"})


def content_key_for_action(action: str) -> str:
    return _ACTION_CONTENT_KEY.get(action, "text")


def content_key_for_type(asset_type: Any) -> str:
    if asset_type is None:
        return "text"
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    return _TYPE_CONTENT_KEY.get(str(type_val), "text")


def normalize_asset_content(
    raw: Any,
    *,
    action: str = "",
    asset_type: Any = None,
    observation: str = "",
    strict: bool = False,
) -> dict[str, Any]:
    """将 LLM 返回的 content（str / list / dict）统一为 TextAsset 所需的 dict。"""
    is_create = action.startswith("create_")
    if strict and is_create:
        observation = ""
    resolved_type = asset_type
    if action in _IMAGE_TEXT_ACTIONS:
        type_map = {
            "create_character": TextAssetType.CHARACTER,
            "update_character": TextAssetType.CHARACTER,
            "create_scene": TextAssetType.SCENE,
            "update_scene": TextAssetType.SCENE,
            "create_prop": TextAssetType.PROP,
            "update_prop": TextAssetType.PROP,
            "create_frame": TextAssetType.FRAME,
        }
        resolved_type = type_map.get(action, resolved_type)

    if action in _VIDEO_CLIP_ACTIONS or resolved_type == TextAssetType.VIDEO_CLIP:
        obs = observation.strip()
        if obs:
            if isinstance(raw, str) and not raw.strip():
                raw = {"video_prompt": obs}
            elif isinstance(raw, dict) and not str(
                raw.get("video_prompt") or raw.get("description") or ""
            ).strip():
                raw = {**raw, "video_prompt": obs}
            elif raw is None:
                raw = {"video_prompt": obs}
        return normalize_video_clip_content(raw)

    if resolved_type and is_image_text_asset(resolved_type):
        obs = observation.strip()
        is_frame = resolved_type == TextAssetType.FRAME or action == "create_frame"
        primary = "image_prompt" if is_frame else "description"
        if obs:
            if isinstance(raw, str) and not raw.strip():
                raw = {primary: obs}
            elif isinstance(raw, dict):
                has_primary = str(raw.get(primary, "")).strip()
                has_legacy = is_frame and str(raw.get("description", "")).strip()
                if not has_primary and not has_legacy:
                    raw = {**raw, primary: obs}
                elif is_frame and not has_primary and has_legacy:
                    raw = {**raw, "image_prompt": str(raw.get("description", "")).strip()}
            elif raw is None:
                raw = {primary: obs}
        return normalize_image_text_content(resolved_type, raw)

    key = content_key_for_action(action) if action else content_key_for_type(asset_type)

    if isinstance(raw, dict) and raw:
        if set(raw.keys()) == {"content"} and isinstance(raw.get("content"), str):
            return {key: raw["content"].strip()}
        if all(isinstance(v, str) for v in raw.values()):
            return dict(raw)
        text_val = raw.get(key) or raw.get("text") or raw.get("content")
        if isinstance(text_val, str) and text_val.strip():
            return {**raw, key: text_val.strip()}
        return dict(raw)

    if isinstance(raw, list):
        parts = [str(item).strip() for item in raw if str(item).strip()]
        if parts:
            return {key: "\n".join(parts)}

    if isinstance(raw, str) and raw.strip():
        if strict and is_create:
            raise ValueError(f"{action} 的 content 必须为对象，不能为字符串。")
        return {key: raw.strip()}

    obs = observation.strip()
    if obs and not (strict and is_create):
        return {key: obs}

    if strict and is_create:
        raise ValueError(f"{action} 缺少 content 或必填字段。")
    return {key: ""}


def validate_create_content(action: str, content: dict[str, Any]) -> None:
    """create_* 路径：强校验结构化 content 必填字段。"""
    from core.llm.prompt.tools.schema_builders import _required_image_text_fields
    from core.models.image_text_asset import (
        CharacterContent,
        CharacterTraits,
        PropContent,
        PropTraits,
        SceneContent,
        SceneTraits,
    )

    if action == "create_plot":
        if not str(content.get("text", "")).strip():
            raise ValueError("create_plot 缺少 content.text")
        return

    type_map = {
        "create_character": (CharacterContent, CharacterTraits),
        "create_scene": (SceneContent, SceneTraits),
        "create_prop": (PropContent, PropTraits),
    }
    if action == "create_frame":
        prompt = str(
            content.get("image_prompt") or content.get("description") or ""
        ).strip()
        if not prompt:
            raise ValueError("create_frame 缺少 content.image_prompt")
        return
    if action == "create_video_clip":
        prompt = str(content.get("video_prompt") or content.get("description") or "").strip()
        if not prompt:
            raise ValueError("create_video_clip 缺少 content.video_prompt")
        return
    pair = type_map.get(action)
    if not pair:
        return
    _content_model, traits_model = pair
    required = _required_image_text_fields(traits_model)
    missing = [f for f in required if not str(content.get(f, "")).strip()]
    if missing:
        raise ValueError(f"{action} 缺少必填字段: {', '.join(missing)}")
    _content_model.model_validate(content)


def extract_llm_content_field(data: dict[str, Any], action: str) -> Any:
    """从 LLM JSON 中提取 content，兼容嵌套 content 或扁平图文字段。"""
    if action in _IMAGE_TEXT_ACTIONS:
        nested = data.get("content")
        if isinstance(nested, dict) and nested:
            return nested
        flat = {
            k: v
            for k, v in data.items()
            if k
            not in (
                "observation",
                "asset_name",
                "asset_id",
                "count",
                "script_md",
                "content_md",
                "title",
            )
            and v is not None
        }
        if flat:
            return flat
    if action in _VIDEO_CLIP_ACTIONS:
        nested = data.get("content")
        if isinstance(nested, dict) and nested:
            return nested
        flat = {
            k: v
            for k, v in data.items()
            if k
            not in (
                "observation",
                "asset_name",
                "asset_id",
                "count",
                "script_md",
                "content_md",
                "title",
            )
            and v is not None
        }
        if flat:
            return flat
    if data.get("content") is not None:
        return data.get("content")
    for field in (
        content_key_for_action(action),
        "text",
        "description",
        "appearance",
        "body",
    ):
        if field in data and data[field] is not None:
            return data[field]
    return None
