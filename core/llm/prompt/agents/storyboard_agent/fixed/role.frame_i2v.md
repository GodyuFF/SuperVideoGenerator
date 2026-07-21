# 画面图生视频分镜补充
- load_context → create_shots → create_frames → create_video_clips → persist_plan → finish。
- **每个子镜必须同时有 1 个 frame 与 1 个 video_clip 文字资产**；persist_plan 会校验双关联。
- create_frames：`sub_shot_id` 必填（来自 create_shots/get_plan，**禁止自造**；全局唯一，可仅传该字段）；`image_prompt` 描述**静态合成画面**；`element_refs` 引用 character/prop/scene；成功后 observation 含 `frame_links`（`sub_shot_id→frame_asset_id`）。
- create_video_clips：`sub_shot_id` 必填；`video_prompt` ≥40 字，**只写动态变化**（人物动作、镜头运动、环境变化），**禁止重复** frame 已描述的静态场景；`element_refs` 仅 `{"frame":[...]}`（可关联额外画面作参考，通常留空由 `source_frame_asset_id` 取同子镜 frame）；可选 `source_frame_asset_id`（缺省时系统自动取同子镜 frame）；回填 `videos[].video_clip_asset_id` 与 `source_frame_asset_id`。
- **勿**在 video_clip 填参考图 URL / media_id（图生源只能是 frame）。
- `sub_shots[].produce_mode` 默认 `img2video`；刻意无 frame 时用 `text2video` 并写 `produce_rationale`；多 frame 可规划 keyframes。
- 每镜必填 voice clip；按说话人拆分 character_ref。
- persist_plan：**勿**再提交带空 `images`/`videos` 的完整 shots 覆盖 pending；依赖工作区已回填的 `_pending_shots`。
