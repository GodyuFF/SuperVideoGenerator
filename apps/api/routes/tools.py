"""REST API：Tool Registry 目录（工具中心）。"""

from fastapi import APIRouter

from core.llm.agent.config_manager import _ALL_AGENT_NAMES
from core.llm.tools import get_tool_registry
from core.llm.tools.agent_tool_config import (
    is_system_tool,
    list_configurable_tool_names,
    list_system_tools,
    system_tool_description,
)
from core.llm.tools.tool_data_scope import governance_payload
from core.llm.tools.tool_taxonomy import lookup_tool_spec, tool_public_view

router = APIRouter(prefix="/api/tools")


def _build_tool_item(agent: str, **kwargs: object) -> dict[str, object]:
    """组装单条工具目录项。"""
    return kwargs | {"agent": agent}


@router.get("")
def list_tools():
    """按 Agent 分组返回 Registry 全量工具（含作用范围、数据边界与治理规则）。"""
    registry = get_tool_registry()
    grouped: dict[str, list[dict[str, object]]] = {}
    catalog: list[dict[str, object]] = []

    for agent in _ALL_AGENT_NAMES:
        specs = registry.list_tools(agent)
        items: list[dict[str, object]] = []
        seen: set[str] = set()

        for action in list_system_tools(agent):
            seen.add(action)
            item = _build_tool_item(
                agent,
                **tool_public_view(
                    agent_name=agent,
                    action=action,
                    name=action,
                    description=system_tool_description(agent, action),
                    kind="system",
                    read_only=True,
                ),
            )
            items.append(item)
            catalog.append(item)

        for spec in specs:
            if is_system_tool(agent, spec.name):
                continue
            seen.add(spec.name)
            item = _build_tool_item(
                agent,
                **tool_public_view(
                    agent_name=agent,
                    action=spec.name,
                    name=spec.name,
                    description=spec.description,
                    kind=spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind),
                    read_only=spec.read_only,
                    spec=spec,
                ),
            )
            items.append(item)
            catalog.append(item)

        for action in list_configurable_tool_names(agent):
            if action in seen:
                continue
            item = _build_tool_item(
                agent,
                **tool_public_view(
                    agent_name=agent,
                    action=action,
                    name=action,
                    description=action,
                    kind="action",
                    read_only=False,
                    spec=lookup_tool_spec(action),
                ),
            )
            items.append(item)
            catalog.append(item)

        grouped[agent] = items

    catalog.sort(key=lambda x: (str(x.get("agent")), str(x.get("action"))))
    return {
        "governance": governance_payload(),
        "agents": grouped,
        "catalog": catalog,
        "registry_version": len(registry.list_tools()),
    }
