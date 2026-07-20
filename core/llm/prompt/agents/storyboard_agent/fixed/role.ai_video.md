# AI 视频模式补充
- 流水线使用 **create_video_clips**，**勿** create_frames。
- `sub_shots[].description` 须描述可被图生视频实现的画面动作。
- 每个子镜填写 `produce_mode`：有参考画面→`img2video`；纯文生→`text2video`；仅静图运镜→`still`；可选 `produce_rationale`。
- 多画面时 `images[]` 填 `start_ms`/`end_ms`（相对镜起点，落在子镜时段内）；省略则等于子镜起止。
- voice clip：按 `voice_speakers` 区分旁白（character_ref 空）与角色对白（character_ref=txt_*）；text 与画面动作一致；单镜时长建议 3–8s。
- `create_video_clips` 每条须含 `sub_shot_id`（来自 create_shots/get_plan，可仅传该字段）、`video_prompt`（≥40 字动作/镜头描述）与 `element_refs`（引用 script_agent 的 character/scene/prop）；可选 `summary` / `notes`（notes 仅 AI 自用）。勿填 `video_mode` / `camera_motion`（系统派生）。
- 可在 `sub_shots[].videos[]` 预规划子镜内多段视频（`media_id` 留空，由 video_agent 回填）。
- persist_plan 前每个子镜必须已关联 video_clip 文字资产。
