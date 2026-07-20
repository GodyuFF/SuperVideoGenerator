# 设计规格：混合意图判定驱动步骤重开（reopen intent）

> 日期：2026-07-17  
> 状态：草案（待实现）  
> 相关：`docs/superpowers/reference/orchestration-state.md`、`core/llm/master/pipeline_progress.py`、`core/llm/master/master_react.py`

---

## 1. 背景与目标

### 1.1 问题

可委派列表由 `session.completed_step_types` 门禁控制：`sub_agents[].available` 与 `delegate_agent` 的 `agent_id` enum 仅包含「未完成且无 hard_blockers」的 agent。

新对话启动时，`seed_completed_steps_for_message` 默认把 Store 推断的完成步写入该集合；仅当用户消息命中 `_REOPEN_STEP_PATTERNS` / `_FULL_REDO_RE` 时才剔除。

结果：用户说「重新设计剧本」等模糊说法时，正则未命中 → `script_agent` 仍为 `completed=true / available=false`，即使 `delegate_readiness.ready=true`，主编排也无法委派。

### 1.2 目标

1. **混合意图判定**：高置信正则优先；未命中且存在 Store 完成步时，用轻量 LLM 判定是否 reopen / full_redo / resume。
2. **门禁仍由 seed 驱动**：不改为「enum 全开、纯靠主编排自觉」；判定结果喂入现有 `seed` → `completed_step_types` → `available_sub_agents`。
3. **失败保守**：LLM 超时、坏 JSON、非法字段 → **不 reopen**，行为等同今日「无正则命中」。
4. **可观测**：判定结果写入 `session.extra["reopen_intent"]`，进入主编排状态 JSON。

### 1.3 非目标

- 取消 hard blockers（风格禁止的步骤仍不可委派）。
- 方案 A（completed 仅提示、enum 始终含全 roster）。
- 在主编排 `delegate_agent` 内嵌「先声明意图再委派」的两阶段协议。
- 用 LLM 列出下游作废列表（仍用 `_DOWNSTREAM_INVALIDATE`）。

---

## 2. 方案选型

| 备选 | 结论 |
|------|------|
| A. 情报/门禁分离，enum 不因 completed 关闭 | 拒绝 — 易误重跑贵步骤 |
| B. enum 全开 + 执行时 `redo_reason` 软确认 | 拒绝 — 本轮不采用 |
| C. 独立意图判定 → 改 seed | **采用** |
| C1. 每轮必打 LLM | 拒绝 — 简单续跑也付费 |
| C2. 仅主编排首轮结构化意图 | 拒绝 — 与委派职责混叠 |
| C3. 正则 + 条件 LLM | **采用** |

失败策略：**保守不 reopen**（保持 Store 复用）。

---

## 3. 流水线

```text
用户消息进入 MasterReActOrchestrator.run()
  → build_pipeline_progress（含 inferred_completed_steps、gaps）
  → resolve_reopen_intent(user_message, progress, style_mode)
        ├─ full_redo 正则命中 → source=regex, full_redo=true
        ├─ detect_reopen_steps 命中 → source=regex, reopen_steps=…
        ├─ inferred_completed 为空 → source=none（无需判定）
        └─ 否则 → 轻量 LLM → source=llm | 失败则 source=none
  → seed_completed_steps_for_message(…, intent=…)
        按 full_redo / reopen_steps 剔除完成态，并对 reopen 步应用 _DOWNSTREAM_INVALIDATE
  → session.extra["reopen_intent"] = intent
  → 现有 delegate_readiness / available_sub_agents / enum 逻辑不变
  → 主编排 decide
```

优先级（固定）：

1. `_FULL_REDO_RE` 命中 → 不再调用 LLM  
2. `detect_reopen_steps` 非空 → 不再调用 LLM  
3. 否则若 `inferred_completed_steps` 非空 → 调用 LLM  
4. LLM 失败 → `source=none`，seed 等同「无 reopen」

---

## 4. 数据契约

### 4.1 `ReopenIntent`

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `"regex" \| "llm" \| "none"` | 判定来源 |
| `full_redo` | bool | 是否清空全部完成态 |
| `reopen_steps` | `list[str]` | 合法 `step_type`；非法项丢弃 |
| `resume_target` | `str \| null` | 可选；非空时写入 `user_resume_target`（覆盖或补强现有 `detect_resume_target_step` 仅当本字段有值） |
| `reason` | str | 一句中文理由（可空） |
| `error` | `str \| null` | 失败摘要；成功为 null |

合法 `step_type` 集合与 pipeline 一致：  
`script_design`、`storyboard`、`image_gen`、`tts_gen`、`shot_detail`、`video_gen`、`edit_compose`。

### 4.2 LLM 输入（短）

- 用户原文（可截断，建议 ≤ 2k 字符）  
- `inferred_completed_steps`  
- `gaps` 前若干条（建议 ≤ 5）  
- `style_mode`  

不注入完整剧本正文或历史对话（控制成本；主编排仍有完整上下文做后续委派）。

### 4.3 LLM 输出（严格 JSON）

```json
{
  "full_redo": false,
  "reopen_steps": ["script_design"],
  "resume_target": null,
  "reason": "用户要求重新设计剧本并补齐实体资产"
}
```

解析规则：

- 必须为对象；缺字段用安全默认（`full_redo=false`，列表空，`resume_target=null`）。  
- `reopen_steps` 过滤非法枚举；`resume_target` 非法则置 null。  
- 未表达重做/续跑 → 空 `reopen_steps` 且 `full_redo=false`。  
- **允许多步**同时出现在 `reopen_steps`；每步仍各自触发 `_DOWNSTREAM_INVALIDATE`。  
- LLM **不必**列出下游；下游作废仅由系统字典完成。

### 4.4 注入主编排状态

`session.extra["reopen_intent"]` 经现有 `build_master_react_state_json` 透传（与 `pipeline_progress` 同级）。  
Prompt 侧补充一句：若 `reopen_intent.reopen_steps` 非空，表示系统已按用户意图重开对应步骤，可委派列表已更新。

---

## 5. 模块落点

| 路径 | 职责 |
|------|------|
| `core/llm/master/reopen_intent.py`（新） | `ReopenIntent`、`resolve_reopen_intent`、正则短路、LLM 调用与解析、失败保守 |
| `core/llm/prompt/...`（新或短 fixed 片段） | 意图判定用 system/user 模板（极短） |
| `core/llm/master/pipeline_progress.py` | `seed_completed_steps_for_message` 接受已解析的 intent（或内部委托 `resolve_reopen_intent` 的纯函数部分）；正则 API 保留 |
| `core/llm/master/master_react.py` | `run()` 启动时调用 `resolve_reopen_intent`，写入 seed 与 `session.extra` |
| `docs/superpowers/reference/orchestration-state.md` | 文档同步：seed 增加 LLM 路径与 `reopen_intent` 字段 |
| `docs/superpowers/reference/prompt-architecture.md` | 动态槽位表增加 `reopen_intent` |

LLM 客户端：复用现有 `LLMClient`；超时与主编排决策调用一致或更短（实现计划中定具体秒数，建议 ≤ 主编排单次上限）。  
测试：仅在 `tests/support/` 提供 scripted 响应；生产路径无 mock。

---

## 6. Seed 语义（不变部分）

在得到 `ReopenIntent` 后：

1. `full_redo` → `completed = ∅`  
2. 否则 `completed = infer_completed_step_types(...)`  
3. 对每个 `reopen_steps` 中的 step：`discard(step)` + `discard` 其 `_DOWNSTREAM_INVALIDATE` 下游  
4. 写入 `session.completed_step_types` / `ctx.completed_step_types`

`available_sub_agents` / tool enum 计算逻辑 **不改**。

正则层可小幅扩充高置信说法（例如「重新设计剧本」），作为零成本路径；LLM 覆盖其余模糊说法。扩充正则不是本设计的阻塞项，实现计划中可选 Task。

---

## 7. 错误处理

| 情况 | 行为 |
|------|------|
| LLM 超时 / 网络错误 | `source=none`，`error` 记录，不 reopen |
| 非 JSON / 解析失败 | 同上 |
| 全部 step 非法被滤空 | 等同不 reopen（`source=llm` 可保留，`reopen_steps=[]`） |
| 无 API Key / 客户端不可用 | 同上保守 |

不向用户弹错；最多在 observation / 状态 JSON 的 `error` 字段留下摘要，主编排按复用 Store 继续。

---

## 8. 验收标准

1. 用户消息含「重新设计剧本」并说明补 character/prop/scene → `script_agent` ∈ `available_sub_agents`，`delegate_agent` enum 含之；`reopen_intent.source` 为 `regex` 或 `llm`。  
2. 「继续做分镜」且无重做意图 → 不误开已完成的 `script_design`。  
3. LLM 超时或坏 JSON → 与当前无 reopen 命中行为一致（Store 完成步仍在 `completed_actions`）。  
4. 「全部重做」「重做剧本」等正则路径 **不** 发起意图 LLM 调用。  
5. 单元测试覆盖：正则短路、LLM 成功 reopen、LLM 失败保守、非法 step 过滤、下游 invalidate。

---

## 9. 测试要点

| 用例 | 期望 |
|------|------|
| `重新写剧本` | `source=regex`，`script_design` 从 seed 剔除，无 LLM |
| `重新设计剧本，补齐角色道具场景` + scripted LLM 返回 reopen script_design | `source=llm`，script 可委派 |
| 同文案但 LLM 抛错 | `source=none`，script 仍 completed |
| `从剪辑继续`（现有 resume 正则） | 行为不回归；意图模块不破坏 `user_resume_target` |
| LLM 返回未知 step | 过滤后不影响合法步 |

---

## 10. 文档与提示词同步

实现完成后必须更新：

- `docs/superpowers/reference/orchestration-state.md` §4.2 Seed、字段一览  
- `docs/superpowers/reference/prompt-architecture.md` 动态槽位（`reopen_intent`）  
- 主编排固定区或状态说明中关于「系统已重开」的一句指引  

---

## 11. 决策记录

| 决策 | 选择 |
|------|------|
| 总方案 | C 独立意图判定改 seed |
| 触发策略 | 混合（正则优先，条件 LLM） |
| LLM 失败 | 保守不 reopen |
| 多步 reopen | 允许；下游由系统字典作废 |
| enum / available | 仍由 `completed_step_types` 决定 |
| resume_target | LLM 可填；有值时写入 `user_resume_target` |
