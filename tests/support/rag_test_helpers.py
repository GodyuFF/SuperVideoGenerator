"""测试辅助：关闭项目 RAG 以便直接创建资产。"""

from __future__ import annotations

from core.store.memory import MemoryStore


def disable_project_rag(store: MemoryStore, project_id: str) -> None:
    """关闭指定项目的 RAG，避免单元测试调用真实 embedding。"""
    project = store.get_project(project_id)
    if project is not None:
        project.config.rag.enabled = False
