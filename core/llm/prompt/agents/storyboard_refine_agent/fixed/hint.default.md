1. **流水线顺序**：get_shot_details → get_shot_asset_timing → sync_actual_assets → **逐镜** review_shot → update_frames → persist_review → finish。

2. get_shot_details 查分镜 plan/detail/配图；get_shot_asset_timing 查音频/视频时长，音频须阅读 `text_segments` 各时段文字。

3. sync_actual_assets 须在 review_shot 之前执行，确保 actual_duration_ms 与 subtitle_segments 已固化。

4. **review_shot（默认）**：每次只复核 **一镜**；必填 `shot_id`；`patch.display_instructions` 必填（含字幕区/画面焦点/运镜节奏）；`restructure_op.op=adjust` 时 **仅传 id + start_ms/end_ms** 增量 patch 子镜/clip/字幕，**勿重复** description/images/videos。

5. **review_and_restructure（跨镜）**：仅用于 split/merge/reorder/add 等跨镜操作；勿把多镜 adjust + patches 塞进一次调用。

6. need_regen 仅在构图与现有 frame 图明显不符时置 true，并说明 regen_reason。

7. update_frames 将 display_instructions 写入 frame notes，供 image_agent 补图参考。

8. persist_review 确认 detail_revision 递增后 finish。get_refine_plan 为只读查询，不替代流水线步骤。

9. **无效 shot_id 或空 patch/restructure_op 会触发 tool preflight 失败**（`ok=false`）；请使用 get_shot_details / get_refine_plan 返回的真实 shot_id。

