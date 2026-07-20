# Skill 与 MCP 扩展开发指南

> 更新日期：2026-07-09

SuperVideoGenerator 支持通过 **pip entry_points** 扩展 Skill（prompt + tool 声明）与 Tool（MCP 语义 Registry），并在 Phase 2 桥接**外部 MCP Server**。

## 1. entry_points 分组

| 分组 | 用途 | 可调用签名 |
|------|------|------------|
| `svg.skills` | 注册 Skill 包 | `() -> SkillBundle \| None` |
| `svg.tools` | 注册 Tool | `(registry: ToolRegistry) -> None` |
| `svg.mcp_servers` | 预声明 MCP Server 模板 | `() -> dict` |

主包 [`pyproject.toml`](../pyproject.toml) 已注册内置 `web_search` 扩展：

```toml
[project.entry-points."svg.tools"]
web_search = "core.extensions.builtin.web_search:register_tools"
```

安装第三方扩展后**重启 API** 生效（不支持热加载）。

## 2. Tool 扩展

### 2.1 契约

- 必须提供完整 `ToolSpec`（含 `input_schema` 与 `output_schema`）
- 扩展 Tool 建议使用 namespace 前缀（如 `ext.hello`），避免与内置 action 冲突
- `source="extension"` 便于审计与 `list_tools(sources=...)`

### 2.2 示例

见 [`examples/svg-ext-template/`](../examples/svg-ext-template/)。

```bash
cd examples/svg-ext-template
pip install -e .
# 重启 uvicorn
```

## 3. Skill 扩展

### 3.1 内置目录

`core/llm/prompt/skills/{id}/`：

- `skill.json` — 元数据，可选 `tools` 字段
- `system.md` — 任务前缀
- `settings.json` — 可选设定
- `agents/{agent_name}.md` — Agent role overlay
- `tools.json` — 可选独立 tool 声明（与 skill.json.tools 二选一）

### 3.2 skill.json tools 字段

```json
{
  "id": "thriller",
  "title": "悬疑短片",
  "tools": {
    "enable": ["web_search"],
    "agents": {
      "script_agent": ["read_webpage", "web_search"]
    },
    "exclude": ["delete_plot"],
    "mcp_servers": ["github"]
  }
}
```

| 字段 | 说明 |
|------|------|
| `enable` | 全局追加可用 tool（如扩展 tool） |
| `agents` | 按 Agent 白名单（覆盖默认 action 集合，保留 finish / ask_user_question） |
| `exclude` | 全局排除 action |
| `mcp_servers` | 激活 Skill 时懒连接 MCP Server |

### 3.3 单轮注入

用户消息 `/skillId 正文` 或 API `skill_id` 参数触发；`skill_overlay` 携带 `tool_manifest` 注入子 Agent 与主编排。

## 4. MCP Server 桥接

### 4.1 配置

运行时配置：[`data/mcp_config.json`](../data/mcp_config.json)

```json
{
  "servers": [
    {
      "id": "my-server",
      "title": "示例 MCP",
      "enabled": false,
      "transport": "stdio",
      "command": "python",
      "args": ["path/to/server.py"],
      "agent": "common",
      "timeout_sec": 30
    }
  ]
}
```

- 默认 **enabled: false**，需用户显式启用
- `transport`: `stdio` | `sse`
- Registry 内 tool 名：`mcp.{server_id}.{tool_name}`

### 4.2 API

- `GET /api/mcp/servers` — 列表与连接状态
- `PUT /api/mcp/servers/{id}` — 更新配置
- `POST /api/mcp/servers/{id}/test` — 连通性测试

### 4.3 依赖

```bash
pip install mcp>=1.7
```

### 4.4 安全

- 拒绝 localhost / 内网 SSE URL
- 单次 `tools/call` 超时（默认 30s）
- 响应文本长度上限 64KB
- 交互日志 `source=mcp`

## 5. 发现与加载顺序

```
get_tool_registry()
  → register_all_tools()      # 内置域
  → load_extension_tools()    # svg.tools entry_points

load_skill(id)
  → svg.skills entry_points（优先）
  → core/llm/prompt/skills/{id}/（内置目录）

FastAPI startup
  → init_mcp_on_startup()     # enabled MCP servers
```

## 6. 相关模块

| 路径 | 职责 |
|------|------|
| [`core/extensions/`](../core/extensions/) | 发现、Skill 合并、Tool 加载、过滤 |
| [`core/extensions/mcp/`](../core/extensions/mcp/) | MCP Client、Adapter、Guard |
| [`core/llm/tools/registry.py`](../core/llm/tools/registry.py) | ToolSpec.source、register_many |
| [`GET /api/skills`](../apps/api/routes/skills.py) | Skill 列表（含 source/tools） |
