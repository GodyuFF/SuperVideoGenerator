# 设计规格：图生视频参考源仅画面+落盘图（有序可重复）

> 日期：2026-07-16  
> 状态：待用户审阅  
> 方案：统一有序槽位列表 `source_refs`（方案 1，已口头确认）

---

## 1. 背景与目标

### 1.1 现状问题

- 图生 / 关键帧可从 **角色 / 场景 / 道具 / 画面 / 落盘图 / video_clip** 多路取参考。
- `source_frame_asset_ids` 与 `source_media_ids` 分栏 + Set 勾选，**无法表达跨类型混排顺序**，也**无法重复绑定**同一画面。
- `video_clip` 的 `element_refs` + `reference_order`（桶级顺序）与「槽位级顺序」语义不符。

### 1.2 目标

1. 图生视频参考源 **仅允许**：`frame`（画面文字资产）、`media`（落盘图片）。
2. **禁止**作为图生参考：character / scene / prop / video_clip。
3. 参考源进入 **一条有序列表**：可混排、可重复；URL 收集严格按列表顺序（重复 id → 重复 URL）。
4. **两处 UI 一致**：video_clip 编辑器 + 分镜 `ShotVideoGenSourcePicker`。
5. 无 `source_refs` 时仍可走 **text2video**（风格允许时）。

### 1.3 非目标

- 不改 Agnes API 协议本身。
- 不改子镜挂接画面（`sub_shots[].images[]`）语义；挂接与「生视频参考槽」仍是两套概念。
- 不把 TTS / 静帧剪辑纳入本变更。

---

## 2. 数据模型

### 2.1 槽位

```ts
type VideoSourceRef = {
  kind: "frame" | "media";
  id: string; // frame → text asset id；media → media asset id
};
```

### 2.2 video_clip content

| 字段 | 变更 |
|------|------|
| `source_refs: VideoSourceRef[]` | **新增**；图生/关键帧唯一参考源 |
| `element_refs`（character/scene/prop/frame） | **删除**作为生视频参考；normalize 时若仍有旧数据：仅把 `frame` 桶按原序展成 `source_refs`，其余桶丢弃 |
| `media_refs` | normalize 时按原序追加为 `{kind:"media", id}`，随后字段废弃或清空 |
| `reference_order` | **删除**；由 `source_refs` 顺序取代 |
| `variant_refs` | 图生路径不再消费角色/道具变体；可保留字段但不参与生视频 URL |

读写：`normalize_video_clip_content` **只产出**含 `source_refs` 的规范结构（单一路径，不做运行时双轨）。

### 2.3 分镜 regenerate / generate API

`video` 请求体：

```json
{
  "sub_shot_idx": 0,
  "source_refs": [
    { "kind": "frame", "id": "txt_frame_…" },
    { "kind": "media", "id": "media_…" },
    { "kind": "frame", "id": "txt_frame_…" }
  ],
  "video_mode": "img2video | keyframes"
}
```

删除（或忽略并不再写入）：`source_frame_asset_ids`、`source_media_ids`、`source_element_refs`、`source_video_clip_asset_ids`。  
读入旧 payload 时：在 API/normalize 层一次性折成 `source_refs`（frames 段 + media 段），**不**保留旧字段出口。

前端 `VideoGenSourceSelection` 同步改为以 `sourceRefs` 为主。

---

## 3. 后端行为

### 3.1 URL 收集

`collect_video_source_image_urls` / `collect_video_clip_source_urls`：

- 输入改为 `source_refs: list[{kind,id}]`。
- **按序**解析 URL；**允许重复**（去掉「同 URL 只保留一次」对用户槽位的压制；若 API 侧必须去重，仅在最终 payload 层记录警告，规格优先保序重复）。
- `kind=frame` → `frame_asset_preview_url`；`kind=media` → `resolve_image_url_for_video`。
- 非法 kind / 找不到资产 → 跳过该项并累计错误（全空则失败）。

### 3.2 模式推断

| `source_refs` 有效 URL 数 | 模式 |
|---------------------------|------|
| 0 | text2video（若允许）或报错 |
| 1 | img2video |
| ≥2 | keyframes（若允许；否则报错或降级策略写清：本规格选 **报错提示需 keyframes 能力**） |

强制 `video_mode` 仍可覆盖推断（校验与 URL 数一致性）。

### 3.3 shot_spec / regenerate

- `resolve_shot_video_gen_spec` / `resolve_video_clip_gen_spec`：显式参考只认 `source_refs`。
- 无显式 refs 时：可回退子镜已挂 frame 图片（现有推断），**不得**再从 character/scene/prop 解析参考图。
- `VideoRegenerateOptions`：字段改为 `source_refs`；`to_generate_args` 只吐新字段。

---

## 4. 前端

### 4.1 统一选择器

组件（可新建 `VideoSourceRefsEditor` 或改造 `ShotVideoGenSourcePicker`）：

- 展示 **有序槽位列表**（序号、kind 徽章、名称缩略图可选）。
- 操作：添加画面、添加落盘图、上移/下移、删除；允许同一 id 多次添加。
- **不展示**：角色 / 场景 / 道具 / video_clip 参考分组。
- 摘要：`N 张参考 → img2video | keyframes`。

### 4.2 挂载点

1. 分镜抽屉生视频区（现 `ShotVideoGenSourcePicker`）。
2. video_clip 编辑 / 详情（现 `AssetRefPicker` 多桶关联 → 改为本选择器；`element_refs` 展示从生视频路径移除）。

### 4.3 i18n

更新 `board.json` 文案：lead / empty / summary；删除 bucket 文案依赖或标废弃。

---

## 5. 测试

| 用例 | 期望 |
|------|------|
| `source_refs` 两 frame 同 id | URL 列表长度 2，顺序一致 |
| frame + media 混排 | URL 顺序与 refs 一致 |
| 旧 content 含 character element_refs | normalize 后无 character；仅迁移 frame/media |
| regenerate body 带旧 `source_element_refs` | 折入或忽略，生视频不使用角色图 |
| 0 refs + 允许 text2video | 文生路径 |
| 前端 count / toApiBody | 只序列化 `source_refs` |

---

## 6. 文档同步

实现后更新：

- `docs/product-plan.md`（分镜二次生成视频参考、video_clip 五块关联）
- `docs/code-design-plan.md`（video 工具 / regenerate options）
- `docs/data-storage.md`（video_clip content 字段）
- 本 spec 状态 → 已实现

---

## 7. 验收标准

1. UI 无法再勾选角色/场景/道具/video_clip 作图生参考。  
2. 同一画面可添加两次且关键帧顺序体现两次。  
3. 画面与落盘图可交错排列，生视频请求顺序一致。  
4. 文生视频在无 refs 时仍可用（风格允许）。  
5. 相关单测与文档已更新；生产路径无 mock。

---

## 8. 风险

| 风险 | 缓解 |
|------|------|
| 历史剧本里角色参考「消失」 | normalize 丢弃非 frame/media；产品预期即禁止 |
| Agnes 对重复 URL 行为未知 | 测一轮；若拒重则在 UI 提示但仍保留槽位语义 |
| AssetRefPicker 仍被 frame 编辑使用 | 勿误删 frame 的 element_refs 编辑器，仅切割 video_clip / 生视频路径 |
