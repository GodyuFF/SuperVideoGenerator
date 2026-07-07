"""主编排声明式确认网关：步骤完成后或高成本动作执行前触发 A2UI。"""

from dataclasses import dataclass

from core.models.entities import TextAssetType
from core.store.memory import MemoryStore


@dataclass(frozen=True)
class GateMeta:
    """确认网关元数据。"""

    title: str
    description: str = ""


CONFIRM_AFTER_STEP: dict[str, GateMeta] = {
    "script_design": GateMeta(
        title="确认剧本结构",
        description="请查看剧本概要，确认后继续、提出修改意见重新生成，或中止流程。",
    ),
}

CONFIRM_BEFORE_ACTION: dict[str, GateMeta] = {}


def build_script_structure_summary(store: MemoryStore, script_id: str) -> str:
    """汇总剧本正文与 plot/character/scene 资产标签，供 script_structure 确认弹窗展示。"""
    script = store.get_script(script_id)
    parts: list[str] = []
    if script and script.content_md.strip():
        parts.append(script.content_md.strip())

    assets = store.list_assets_for_script(script_id)
    by_type: dict[TextAssetType, list[str]] = {}
    for asset in assets:
        by_type.setdefault(asset.type, []).append(asset.name)

    labels = {
        TextAssetType.PLOT: "剧情",
        TextAssetType.CHARACTER: "人物",
        TextAssetType.SCENE: "场景",
    }
    for asset_type, heading in labels.items():
        names = by_type.get(asset_type, [])
        if names:
            parts.append(f"**{heading}**：{', '.join(names)}")

    return "\n\n".join(parts) if parts else "（暂无剧本内容，请确认是否继续）"
