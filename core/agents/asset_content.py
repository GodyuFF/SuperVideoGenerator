"""文字资产 content 字段规范化（LLM 常返回字符串或非标结构）。"""

from typing import Any

from core.models.entities import TextAssetType

_ACTION_CONTENT_KEY: dict[str, str] = {
    "create_plot": "text",
    "update_plot": "text",
    "create_character": "appearance",
    "update_character": "appearance",
    "create_scene": "description",
    "update_scene": "description",
}

_TYPE_CONTENT_KEY: dict[str, str] = {
    TextAssetType.PLOT.value: "text",
    TextAssetType.CHARACTER.value: "appearance",
    TextAssetType.SCENE.value: "description",
    TextAssetType.NARRATION.value: "text",
    TextAssetType.PROP.value: "description",
}


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
) -> dict[str, Any]:
    """将 LLM 返回的 content（str / list / dict）统一为 TextAsset 所需的 dict。"""
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
        return {key: raw.strip()}

    obs = observation.strip()
    if obs:
        return {key: obs}

    return {key: ""}


def extract_llm_content_field(data: dict[str, Any], action: str) -> Any:
    """从 LLM JSON 中提取 content，兼容 text / description / appearance 等字段。"""
    if data.get("content") is not None:
        return data.get("content")
    for field in (content_key_for_action(action), "text", "description", "appearance", "body"):
        if field in data and data[field] is not None:
            return data[field]
    return None
