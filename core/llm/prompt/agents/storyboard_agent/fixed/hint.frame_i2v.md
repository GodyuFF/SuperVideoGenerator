画面图生视频分镜：
1. create_shots：每子镜 produce_mode 默认 img2video；记下返回的 sub_shots[].id
2. create_frames：条数=子镜数；每条 `sub_shot_id` + `image_prompt` + `element_refs`；读返回 `frame_links`
3. create_video_clips：条数=子镜数；`video_prompt` 仅写动态；`element_refs` 仅 `{"frame":[...]}`；`source_frame_asset_id` 可省略（系统自动绑同子镜 frame）
4. persist_plan：勿重传空 images/videos；确认 frame 与 video_clip 双关联后保存
