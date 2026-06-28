# 提示词架构（core/prompt）

> 更新日期：2026-06-28

本文档描述 SuperVideoGenerator 中 Agent 提示词的 **固定区 / 动态区** 分层设计，参考 Claude Code 的 system prompt 组装模式。

## 1. 设计原则

| 概念 | Claude Code | 本项目 |
|------|-------------|--------|
| 固定区 | system prompt 中可缓存的静态段落 | `rules/*.md` + `agents/*/fixed/*.md` → **system** |
| 动态区 | 会话/环境/历史等运行时内容 | 模板槽位 + Store 快照 → **user** |
| 项目规则 | CLAUDE.md 注入对话 | 项目 `role_prompt` override（`prompt_resolver`） |
| 按需加载 | Skills / MCP | `PromptProfile`（default / dynamic_image / ai_video） |

**边界约定**：LLM 调用时 `system` 仅含固定区；`user` 含全部动态上下文（ReAct XML 或行动文本）。

## 2. 目录结构

```
core/prompt/
├── builder.py              # PromptBuilder：组装 system / user
├── context_manager.py      # 每 Agent 动态槽位 Provider
├── context_window.py       # observation / 历史滑窗压缩
├── registry.py             # 加载 fixed 提示词、PromptProfile
├── loader.py
├── config.py
├── rules/
│   ├── react_xml.md        # 全局 ReAct XML 输出协议
│   └── action_json.md      # 全局 JSON 输出协议（通用规则）
├── templates/
│   ├── react_context.xml   # 子 Agent ReAct 动态 user 模板
│   ├── react_session.xml   # 主编排 ReAct 动态 user 模板
│   └── action_context.txt  # 行动执行动态 user 模板
└── agents/{agent_name}/
    └── fixed/
        ├── role.default.md
        ├── role.dynamic_image.md   # 可选
        ├── role.ai_video.md        # 可选
        ├── actions.md              # 该 Agent JSON 字段说明
        ├── hint.{profile}.md       # 模式补充（拼入 action system）
        ├── intent.md               # 对话入口意图门卫（LLM JSON）
        └── summary.md              # 仅 super_video_master
```

### 固定提示词分段格式（role.*.md）

每个 Agent 的 `role.{profile}.md` 采用统一 Markdown 结构：

- **Identity**：角色身份
- **Capabilities**：能做什么 / 不能做什么
- **Actions**：流水线 / ad_hoc / 只读行动
- **Constraints**：业务约束
- **Collaboration**：与主编排及其他 Agent 的协作关系

## 3. 两条 LLM 调用链

### 3.1 ReAct 决策（选 action）

```
system: build_react_system()           ← rules/react_xml.md
user:   build_react_user(slots)        ← templates/react_context.xml
        slots 由 AgentContextManager.sub_agent 填充
```

主编排使用 `templates/react_session.xml`（含 sub_agents、tools）。

### 3.2 行动执行（JSON observation）

```
system: build_action_system(agent, profile)
        ← rules/action_json.md + fixed/actions.md + fixed/hint.*
user:   build_action_user(slots)
        ← templates/action_context.txt
        slots 含 store 快照、历史观察、当前 action
```

## 4. 动态槽位

| 槽位 | 来源 | ReAct | Action |
|------|------|-------|--------|
| `role_description` | `resolve_agent_prompts` | ✓ | ✓（user 内） |
| `task_brief` | 主编排委派 / 会话 | ✓ | ✓ |
| `available_actions` | `tools/specs.py` | ✓ | — |
| `completed_actions` | `AgentRunContext` | ✓ | ✓ |
| `observations` | `PreparedContext`（滑窗压缩） | ✓ | ✓ |
| `history_summary` | `context_window` | ✓ | ✓ |
| `store_context` | MemoryStore 快照 | — | ✓ |
| `style_mode` / `iteration` | work_context / extra | ✓ | — |

子 Agent 会话历史由 `ConversationStore` 按 `(script_id, agent_name)` 隔离；压缩逻辑见 `context_window.py`。

## 5. Profile 解析优先级

`core/agents/prompt_resolver.py`：

1. 项目 `role_prompt` 覆盖（仅 role，hint 仍跟 profile）
2. 项目 `prompt_profile`
3. 全局 `agent_config.json` 的 profile
4. `VideoStyleMode` → `PromptProfile` 映射
5. `DEFAULT`

## 6. 扩展新 Agent  checklist

1. 在 `core/agents/tools/specs.py` 定义 `AGENT_TOOLS`
2. 创建 `core/prompt/agents/{name}/fixed/role.default.md`（及 profile 变体）
3. 创建 `fixed/actions.md` 列出 JSON 字段
4. 在 `registry._AGENT_NAMES` 注册（若需出现在设置页 profile 列表）
5. 运行 `pytest tests/unit/test_agent_prompts.py`

## 7. 相关代码入口

| 模块 | 职责 |
|------|------|
| [`core/prompt/builder.py`](../core/prompt/builder.py) | 固定/动态组装 |
| [`core/prompt/context_manager.py`](../core/prompt/context_manager.py) | 动态槽位 |
| [`core/agents/base.py`](../core/agents/base.py) | 子 Agent ReAct / action 入口 |
| [`core/llm/react_decider.py`](../core/llm/react_decider.py) | 子 Agent ReAct LLM 调用 |
| [`core/llm/react.py`](../core/llm/react.py) | 主编排 ReAct LLM 调用 |
| [`core/super_video_master/actions.py`](../core/super_video_master/actions.py) | STEP_META 描述从 role 摘要加载 |
| [`core/super_video_master/intent.py`](../core/super_video_master/intent.py) | 对话入口 LLM 意图门卫（`fixed/intent.md`） |

## 8. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-28 | 对话入口意图判断改为 LLM 分类（`intent.md`），移除关键词硬编码拦截 |
| 2026-06-24 | 引入 fixed/dynamic 分层、`PromptBuilder`、`AgentContextManager`；7 个 Agent 提示词重写为 Claude Code 分段格式 |
| 2026-06-25 | 修复 TextAsset content 验证错误：修改 script_agent actions.md 与 role.default.md 及全局 action_json.md，明确要求 content 必须为对象（dict），禁止字符串；LLM 现按规范返回对象，normalization 保留兜底 |
