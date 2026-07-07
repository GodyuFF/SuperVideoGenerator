# 动态图文 · 剪辑规划补充

- 须遵守 **edit_capabilities.md** 中的运镜/转场/背景枚举；勿规划未实现的效果；**禁止**自造 gentle_* / slow_* 运镜名。
- plan_edit_timeline 时优先输出 **video_layers**（多视频图层数组）：主画面 `z_index=0`；画中画/贴纸放更高层；**最多 5 层**（`max_video_layers`）。
- **同一 video_layer 内 clip 时间不得重叠**；多角色同时出现须拆到独立 `video_layers`（每层一条时间线），跨层可重叠。
- 规划后读 `layer_summary.warnings` 与 `same_layer_overlaps`；若有同层重叠警告，须调整后再 compose_final。
- 每个 video clip 必须包含 **transform**（`x/y/width/height` 归一化 0–1，默认全屏 `0.5,0.5,1,1`）与 **asset_ref** 或 **source_refs** 指向已生成 media。
- 每段须写清 Ken Burns 起止焦点（motion_detail.from_focal / to_focal）、缩放（scale_from/scale_to）、与上一段转场（transition_in）、背景（纯色或 scene 图 asset_ref）。
- 视频轨仅使用 context 中 media.image.items 里 is_accessible=true 的素材；优先 source_refs 关联角色/场景文字资产。
- **tracks.audio[]** 每镜须填 `asset_ref`（load_edit_context 中对应镜头的 `audio_media_id`）；**tracks.subtitle[] 由后端从 TTS subtitle_cues 自动生成**，Agent 无需手写逐句字幕。若 LLM 漏写 audio 轨，后端会从 Store TTS 自动补齐。
- **缩放**：画布缩放用 `transform.width/height`（1.0=全屏，0.3=画中画）；片内运镜缩放用 `motion_detail.scale_from/to`，二者叠加。
