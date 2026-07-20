画面图生视频分镜：
1. create_shots：每子镜 produce_mode 默认 img2video
2. create_frames：条数=子镜数；image_prompt + element_refs
3. create_video_clips：条数=子镜数；video_prompt 仅写动态；source_frame_asset_id 绑定 frame
4. persist_plan 前确认 frame 与 video_clip 双关联完整
