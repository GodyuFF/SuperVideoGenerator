# 设计规格：图片 / 视频统一生成队列（MVP）

> 日期：2026-07-16  
> 状态：**已实现**（2026-07-16）；实现计划见 `docs/superpowers/plans/2026-07-16-generation-queue.md`  

> 范围：进程内串行队列 + WebSocket 快照 + 工作台右侧抽屉展示

---

## 1. 背景与目标

### 1.1 问题

- Agnes 视频创建约 **1 次/分钟**；状态查询与创建叠压会触发 429。
- 生图有并发与 `image_gen_progress`；生视频无统一待办视图。
- 前端 `AssetGenerationContext` / 印样台批量仅覆盖部分入口，**没有**「待生成列表」侧栏。

### 1.2 目标（MVP）

1. **统一队列**：图片与视频任务进入同一串行队列（同一时刻只执行 1 条）。
2. **上一条完成再下一条**：工人循环 `dequeue → run → 推送快照`。
3. **侧栏可见**：右侧抽屉展示排队 / 进行中 / 完成 / 失败。
4. **入口覆盖**：二次生成、批量 regenerate、Agent 侧 `generate_images` / `generate_video_clips`（批任务拆条入队）。

### 1.3 非目标（完整版再做）

- 拖拽排序、整队暂停、单项取消以外的复杂控制。
- 跨进程 / 重启后的队列持久化。
- TTS 纳入本队列（可后续扩展 `kind`）。

---

## 2. 方案选型

采用 **后端全局调度器（方案 A）**：

| 备选 | 结论 |
|------|------|
| A. 后端 `GenerationQueue` + WS | **采用** — 侧栏与限流一致 |
| B. 仅前端串行 | 拒绝 — Agent 批跑不受控 |
| C. 仅调低 Semaphore | 拒绝 — 无待生成视图 |

---

## 3. 领域模型

### 3.1 任务 `GenerationJob`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | `gen_` 前缀 |
| `script_id` | string | 所属剧本 |
| `project_id` | string | 项目 |
| `kind` | `"image" \| "video"` | 媒体类型 |
| `asset_id` | string | 文字资产 ID（character/scene/prop/frame/video_clip） |
| `label` | string | 展示名 |
| `status` | `"queued" \| "running" \| "done" \| "failed"` | |
| `error` | string \| null | 失败摘要 |
| `variant_id` | string \| null | 可选，指定形象变体 |
| `created_at` / `started_at` / `finished_at` | ISO 或 epoch ms | |
| `source` | `"regenerate" \| "batch" \| "agent"` | 入队来源 |

去重策略（MVP）：同一 `script_id + kind + asset_id + (variant_id or "")` 若已有 `queued|running`，**不重复入队**，返回已有 job id。

### 3.2 队列 `GenerationQueue`

- 进程内单例；内部按 **全局一条工人** 串行（不按剧本并行工人，以免多剧本同时打 Agnes）。
- 内存结构：`deque` 待执行 + `jobs: dict[id, GenerationJob]` + 可选最近 N 条已完成（默认保留 50）。
- 服务重启清空；不写盘。

---

## 4. 后端接口与事件

### 4.1 模块落点

| 路径 | 职责 |
|------|------|
| `core/generation/queue.py` | 队列、入队、工人、快照 |
| `core/generation/runner.py` | 调用现有 regenerate / image·video generate 单条执行 |
| `apps/api/routes/generation_queue.py` | HTTP：列表 / 入队（可选） |
| 现有 regenerate / tool handler | 改为「入队」或「入队并等待当前 job」 |

### 4.2 HTTP（MVP）

```
GET  /api/projects/{pid}/scripts/{sid}/generation-queue
POST /api/projects/{pid}/scripts/{sid}/generation-queue/enqueue
     body: { kind, asset_id, variant_id?, label? }
```

- `GET`：返回该剧本相关 jobs（queued/running + 最近完成）。
- 二次生成 API 可改为：入队后立即 202 + `{ job_id, queue }`，由队列执行（与现异步 regenerate 对齐）。

### 4.3 WebSocket

事件类型：`generation_queue_snapshot`

```json
{
  "type": "generation_queue_snapshot",
  "script_id": "...",
  "project_id": "...",
  "active": { "...job..." },
  "queued": [ "...jobs..." ],
  "recent": [ "...done/failed..." ],
  "counts": { "queued": 3, "running": 1 }
}
```

推送时机：入队、开始执行、完成/失败、（可选）每条进度节流合并后。

兼容：保留现有 `image_gen_progress` / `assets_changed`；前端徽章继续可用。新增 `video_gen_progress`（可选，MVP 可用 snapshot 的 running 状态代替）。

### 4.4 执行适配

- **image**：复用 `regenerate_asset` / 单条 image generate 路径（含 variant_id）。
- **video**：复用 `handle_generate_video_clips` 限定单 `asset_id`；创建侧继续走已有 Agnes `create_min_interval_sec`。
- Agent 批量：`run_concurrent_image_generation` / `run_concurrent_video_clip_generation` 改为「拆条入队 + 等待本批全部 done/failed」（或入队后 observation 返回已入队数量）；**禁止**绕过队列直接高并发打 API。

取消：MVP 仅支持「从 queued 移除」（可选 API）；`running` 依赖现有 `ExecutionCancelled` / abort 体系，本阶段可不做单项取消。

---

## 5. 前端

### 5.1 侧栏 `GenerationQueueDrawer`

- 模式对齐 `BatchAssetStudioDrawer`：`backdrop` + 右侧 `aside` + `useResizableDrawerWidth`。
- 分区：进行中 → 排队中 → 最近完成/失败。
- 行：kind 徽章、名称、asset_id 短码、状态、失败摘要。
- 挂载：`Workbench` 或 `BoardPanel`；顶栏/看板角标显示 `queued + running` 数量，点击打开。

### 5.2 状态订阅

- WS：`generation_queue_snapshot` → Context（新建 `GenerationQueueContext` 或扩展 `AssetGenerationContext`）。
- 打开抽屉时 `GET` 拉一次快照防漏事件。

### 5.3 入口改造

- `AssetRegenerateButton` / 批量印样：走 enqueue（或现有 regenerate 已改入队）。
- 乐观 `markGenerating` 可保留，以 snapshot 为准校正。

### 5.4 i18n / 样式

- 中英 `board` 或 `common` 文案；令牌 `--svf-*`；中文 JSDoc。

---

## 6. 测试

| 层级 | 用例 |
|------|------|
| unit | 入队去重；串行顺序（mock runner）；失败后继续下一条 |
| unit | snapshot 形状 |
| api（可选） | GET/POST enqueue |
| 前端 | Context reduce；抽屉空态/列表（轻量） |

禁止在 `core/` 生产路径写 mock；测试用 `tests/support`。

---

## 7. 文档同步

实现完成后更新：

- `docs/superpowers/reference/code-design-plan.md`（生成队列模块 + API）
- `docs/superpowers/reference/product-plan.md`（工作台侧栏能力一句）
- `docs/superpowers/reference/frontend-style-guide.md`（抽屉模式）
- `.env.example`（若有队列相关开关；MVP 可不加）

---

## 8. 里程碑

1. `core/generation/queue.py` + 单测串行  
2. runner 接入 regenerate / video_clip 单条  
3. WS snapshot + HTTP GET  
4. 改造 regenerate / agent 批处理入队  
5. `GenerationQueueDrawer` + 角标  
6. 文档与回归测试  

---

## 9. 风险

| 风险 | 缓解 |
|------|------|
| 长队列阻塞对话体感 | 侧栏可见进度；observation 标明「已入队 N 条」 |
| 与 Agnes 创建间隔叠加过慢 | 预期行为；文案提示约 1 视频/分钟 |
| 双路径绕过队列 | Code review：生成入口统一经 enqueue |

---

## 10. 验收标准

1. 连续入队多个 image + video，侧栏可见排队，且 **同时只有 1 条 running**。  
2. 上一条 done/failed 后自动开始下一条。  
3. 二次生成 / 批量 / Agent 生视频均出现在同一队列。  
4. 刷新页面后可通过 GET + WS 恢复当前内存队列视图（进程未重启）。  
5. 进程重启后队列为空（文档已说明）。
