# Agent 交互流程验证结果

**验证日期**：2026-06-24（提示词架构升级后更新）
**测试文件**：`tests/unit/test_agent_flow.py`、`tests/unit/test_prompt_builder.py`

---

## 验证目标

验证 Agent 提示词 **固定区 / 动态区** 分层后的交互流程：

1. `core/prompt/agents/*/fixed/role.*.md` 经 `registry` + `prompt_resolver` 解析为 `role_prompt`
2. `ReActAgent.resolve_role_prompt` 将 role 传入 `decide_agent`
3. `AgentContextManager.sub_agent.build_react_inputs` 组装动态槽位
4. `PromptBuilder.build_react_user` 渲染 `templates/react_context.xml`，`<role>` 含固定角色说明
5. 行动执行：`build_action_system`（固定）+ `build_action_user`（动态）

---

## 数据流

```
fixed/role.*.md ──► prompt_resolver ──► role_prompt
                                              │
PreparedContext ◄── context_window ◄── ConversationStore
       │                                      │
       └────► AgentContextManager ──► PromptBuilder.build_react_user ──► LLM user
rules/react_xml.md ──► PromptBuilder.build_react_system ──► LLM system
```

---

## 测试状态

| 测试 | 状态 |
|------|------|
| `test_agent_role_prompt_flow_to_xml` | ✅ patch `build_react_user` 验证传递链 |
| `test_role_prompt_in_decide_method` | ✅ decide 传递 role_prompt |
| `test_prompt_builder.py` | ✅ 模板渲染与 action system 含 actions.md |
| `test_context_manager.py` | ✅ 子 Agent 动态槽位 |
| `test_prompt_registry.py` | ✅ fixed 路径加载与 role 分段格式 |

运行：`pytest tests/unit/test_agent_flow.py tests/unit/test_prompt_builder.py -q`

---

## 历史说明

2026-06-16 版本曾记录提示词集中在 `definitions.py`；自 2026-06-24 起已迁移至 `core/prompt/`，`definitions.role_prompt` 仅作展示默认，运行时以 `fixed/role.*.md` 为准。
