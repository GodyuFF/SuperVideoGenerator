"""MCP Server 配置模型与持久化。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.store.project_paths import resolve_data_root

DEFAULT_MCP_CONFIG_PATH = resolve_data_root() / "mcp_config.json"


@dataclass
class McpServerConfig:
    """单个 MCP Server 连接配置。"""

    id: str
    title: str = ""
    description: str = ""
    enabled: bool = False
    transport: str = "stdio"  # stdio | sse
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    timeout_sec: float = 30.0
    agent: str = "common"
    allowed_tools: list[str] | None = None
    tool_prefix: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> McpServerConfig:
        """从 JSON 对象解析配置。"""
        server_id = str(raw.get("id", "")).strip()
        args_raw = raw.get("args") or []
        args = [str(a) for a in args_raw] if isinstance(args_raw, list) else []
        env_raw = raw.get("env") or {}
        env = {str(k): str(v) for k, v in env_raw.items()} if isinstance(env_raw, dict) else {}
        allowed = raw.get("allowed_tools")
        allowed_tools = (
            [str(t).strip() for t in allowed if str(t).strip()]
            if isinstance(allowed, list)
            else None
        )
        return cls(
            id=server_id,
            title=str(raw.get("title", server_id)),
            description=str(raw.get("description", "")),
            enabled=bool(raw.get("enabled", False)),
            transport=str(raw.get("transport", "stdio")).strip().lower() or "stdio",
            command=str(raw.get("command", "")).strip(),
            args=args,
            env=env,
            url=str(raw.get("url", "")).strip(),
            timeout_sec=float(raw.get("timeout_sec", 30.0)),
            agent=str(raw.get("agent", "common")).strip() or "common",
            allowed_tools=allowed_tools,
            tool_prefix=str(raw.get("tool_prefix", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好结构。"""
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "enabled": self.enabled,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "url": self.url,
            "timeout_sec": self.timeout_sec,
            "agent": self.agent,
        }
        if self.allowed_tools is not None:
            out["allowed_tools"] = list(self.allowed_tools)
        if self.tool_prefix:
            out["tool_prefix"] = self.tool_prefix
        return out


class McpConfigStore:
    """读写 data/mcp_config.json。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_MCP_CONFIG_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[McpServerConfig]:
        """加载全部 server 配置。"""
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        servers_raw = raw.get("servers") if isinstance(raw, dict) else raw
        if not isinstance(servers_raw, list):
            return []
        result: list[McpServerConfig] = []
        for item in servers_raw:
            if not isinstance(item, dict):
                continue
            cfg = McpServerConfig.from_dict(item)
            if cfg.id:
                result.append(cfg)
        return result

    def save(self, servers: list[McpServerConfig]) -> None:
        """持久化 server 列表。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"servers": [s.to_dict() for s in servers]}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, server_id: str) -> McpServerConfig | None:
        """按 id 查找配置。"""
        for cfg in self.load():
            if cfg.id == server_id:
                return cfg
        return None

    def upsert(self, config: McpServerConfig) -> None:
        """新增或更新单个 server。"""
        servers = self.load()
        replaced = False
        for idx, cfg in enumerate(servers):
            if cfg.id == config.id:
                servers[idx] = config
                replaced = True
                break
        if not replaced:
            servers.append(config)
        self.save(servers)


def load_entry_point_server_defs() -> dict[str, dict[str, Any]]:
    """从 svg.mcp_servers entry_points 加载预声明 server 模板。"""
    from core.extensions.discovery import iter_entry_points
    from core.extensions.constants import ENTRY_GROUP_MCP_SERVERS

    result: dict[str, dict[str, Any]] = {}
    for name, ep in iter_entry_points(ENTRY_GROUP_MCP_SERVERS):
        try:
            fn = ep.load()
            raw = fn()
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        server_id = str(raw.get("id", name)).strip()
        if server_id:
            result[server_id] = raw
    return result
