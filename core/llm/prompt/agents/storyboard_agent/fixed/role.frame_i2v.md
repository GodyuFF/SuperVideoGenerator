# 画面图生视频分镜补充
- load_context → create_shots → create_frames → create_video_clips → persist_plan → finish。
- **每个子镜必须同时有 1 个 frame 与 1 个 video_clip 文字资产**；persist_plan 会校验双关联。
- create_frames：`sub_shot_id` 必填；`image_prompt` 描述**静态合成画面**；`element_refs` 引用 character/prop/scene；绑定 `sub_shots[].images[].frame_asset_id`。
- create_video_clips：`sub_shot_id` 必填；`video_prompt` ≥40 字，**只写动态变化**（人物动作、镜头运动、环境变化），**禁止重复** frame 已描述的静态场景；回填 `sub_shots[].videos[].video_clip_asset_id`；**必须**设置 `sub_shots[].videos[].source_frame_asset_id` = 对应 frame 的 asset_id。
- **勿**在 video_clip 填参考图 URL / media_id（图生源只能是 frame）。
- `sub_shots[].produce_mode` 默认 `img2video`；刻意无 frame 时用 `text2video` 并写 `produce_rationale`；多 frame 可规划 keyframes。
- 每镜必填 voice clip；按说话人拆分 character_ref。
