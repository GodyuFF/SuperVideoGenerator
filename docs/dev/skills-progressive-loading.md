# Skill 渐进加载机制

> 更新日期：2026-07-22

对齐 [Claude Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) / [Cursor Skills](https://cursor.com/docs/skills) 的三层渐进披露，适配本仓库显式激活 + 多 Agent ReAct。

## 三层模型

| 层 | 本仓库映射 | 进上下文时机 |
|----|------------|--------------|
| L1 Metadata | `skill.json` + `GET /api/skills` | Picker / `tool_list_skills` |
| L2 Instructions | 精简 `system.md` + `agents/<name>.md` | Skill 激活后注入 |
| L3 Resources | `references/` + 索引 | 激活时只注入**索引**；正文靠 `read_skill_ref` |

## 目录约定

```text
core/llm/prompt/skills/
  *.py                    # loader / allowlist（运行可产生 __pycache__/，已 gitignore）
  .gitignore              # 忽略本目录 __pycache__/
  builtin/<id>/           # 内置 Skill 内容包（与 .py 分离，避免缓存目录混入配方）
    skill.json            # 含 title / description / aliases / highlights（作用要点）
    system.md
    settings.json
    agents/<agent_name>.md
    references/
```

**约定**：内容包只放 `builtin/<id>/`；`list_skills` 跳过以 `.` / `__` 开头的目录。
## 激活优先级（1C）

1. 本轮显式 `/skillId` 或 API `skill_id`
2. 否则沿用对话 `Conversation.active_skill_id`
3. 本轮主编排 `tool_switch_skill`（建议先 `ask_user_question` 确认）

## 工具

| 工具 | 角色 |
|------|------|
| `list_skill_refs` / `read_skill_ref` | 子 Agent（Skill 激活时自动追加） |
| `tool_list_skills` | 主编排常驻 |
| `tool_list_skill_refs` / `tool_read_skill_ref` | 主编排 |
| `tool_switch_skill` | 主编排切换/清除 |

单次正文默认上限 8000 字符；路径限制在该 Skill 的 `references/` 下。

## 内置示例

- `short_drama` / `villain` / `微短剧`：微短剧全流程（选题→分集→合规），参考知识库来自 [0xsline/short-drama](https://github.com/0xsline/short-drama)（MIT）；`references/` 含 8 份专业文档

## 人工导入与按 Agent 白名单

| 能力 | 说明 |
|------|------|
| 管理页 | `#/skills` Skill 库：列表、拖放导入、格式校验清单、删除用户包 |
| 校验 | `POST /api/skills/validate`（不落盘）；导入前强制同一套检查（`skill.json` / id / `system.md` 等） |
| 导入 | `POST /api/skills/import` → `data/skills/<id>/`；同 id 需确认覆盖 |
| 删除 | `DELETE /api/skills/{id}`（仅用户）；并清理 `skill_allowlists_by_profile` 引用 |
| 加载优先级 | extension > user > builtin |
| 关联 | Agent 配置页（`#/agents`）按 Profile×Agent 勾选；无导入/删除 |
| 语义 | Agent **无**键 → 全部可用；有键且 `[]` → 禁用全部 |
| 运行时 | `/skillId`、Workbench picker、`tool_list_skills` / `tool_switch_skill` 按主编排白名单；委派按子 Agent 白名单 |
| 列表过滤 | `GET /api/skills?profile=&agent=` |
