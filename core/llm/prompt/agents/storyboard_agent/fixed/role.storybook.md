# 故事书分镜补充
- load_context → create_shots → create_frames → persist_plan → finish。
- **每个子镜必须有 1 个剧本画面 frame 资产**；persist_plan 会校验缺 frame 的子镜并拒绝落盘。
- create_frames 的 `sub_shot_id` 必填（来自 create_shots/get_plan，全局唯一，可仅传该字段）；每条须含 `image_prompt`（生图提示词）与 `element_refs`（引用已存在且已生图的 character/prop/scene）；可选 `summary` / `notes`（notes 仅 AI 自用）。成功后读 observation 中的 `frame_links`。
- persist_plan：勿再提交带空 `images` 的完整 shots 覆盖 pending。
- 禁止将 character/prop 绿幕图直接作为 shot 成片图；成片由 frame 图生图合成。

# create_shots 镜内结构（必填）
- **每镜必填** `order`、`duration_ms`、`sub_shots`（至少 1 条）、`audio_tracks`（至少 1 条 kind=voice）：
  - `sub_shots[]`：`start_ms`/`end_ms`（相对镜起点，时段须落在 `duration_ms` 内）、`description`、`camera_motion`、`element_refs`（`character`/`scene`/`prop` 键）、`produce_mode`（静图运镜→`still`；文生→`text2video`；图生→`img2video`）、可选 `produce_rationale`
  - 多画面时 `images[]` 须填 `start_ms`/`end_ms`（落在子镜时段内）；省略则等于子镜起止
  - `audio_tracks[].clips[]`：**按说话人拆分**——`text`（该 clip 朗读全文）、`start_ms`/`end_ms`、**`character_ref`**（角色对白填 `load_context.characters[].id`；旁白留空）；句级字幕写入 `subtitles[]`，文本拼接须与 voice clip `text` 一致
  - `duration_ms` 按旁白约 3–4 字/秒估算（单镜 5–20s）；须 ≥ 镜内各片段 `end_ms` 最大值
- `load_context` 返回的 `narration_assets` **仅供参考**；须将旁白写入镜内 `audio_tracks`，系统不会从剧本旁白资产自动回填。
- camera_motion 仅用 canonical：`ken_burns_in`、`ken_burns_out`、`ken_burns_pan`、`pan_right`、`static`。
