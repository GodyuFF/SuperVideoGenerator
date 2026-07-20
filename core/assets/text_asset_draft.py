"""工作台图文资产 AI 草稿生成服务入口。"""

from __future__ import annotations

from typing import Any

from core.guards.reference import ScriptEditGuard, ScriptEditGuardError
from core.llm.client import LLMClient
from core.llm.client.settings import LLMConfigManager
from core.llm.tools.workbench.generate_text_asset_draft import generate_text_asset_draft
from core.store.memory import MemoryStore


async def generate_text_asset_draft_for_script(
    store: MemoryStore,
    llm_config: LLMConfigManager,
    *,
    project_id: str,
    script_id: str,
    asset_type: str,
    summary: str,
    name: str = "",
    hints: dict[str, Any] | None = None,
    interaction_recorder: Any | None = None,
) -> dict[str, Any]:
    """在可编辑剧本下调用 LLM 生成图文资产草稿 JSON。"""
    script = store.get_script(script_id)
    if not script:
        raise ValueError(f"剧本 {script_id} 不存在")
    if script.project_id != project_id:
        raise ValueError(f"剧本 {script_id} 不属于项目 {project_id}")
    if not ScriptEditGuard.is_editable(script):
        raise ScriptEditGuardError(
            f"剧本 {script_id} 状态为 {script.status}，AI 执行中不可生成草稿"
        )

    llm_client = LLMClient(llm_config, interaction_recorder)
    return await generate_text_asset_draft(
        llm_client,
        store,
        project_id=project_id,
        script_id=script_id,
        asset_type=asset_type,
        summary=summary,
        name=name,
        hints=hints,
        log_context={
            "project_id": project_id,
            "script_id": script_id,
            "source": "workbench",
        },
    )
