漫画/动态图模式：
1. create_shots：`sub_shots` + voice `audio_tracks` 均必填；多子镜时段须落在 `duration_ms` 内；`camera_motion` **仅**可使用 edit_capabilities 枚举或别名（如 ken_burns_in、fade、pan），**禁止**自造 gentle_push_in / slow_zoom_in 等名称。
2. `sub_shots[].element_refs` 用 character/scene/prop 键；禁止 asset_id 键。
3. 每个子镜须 create_frames（`sub_shot_id` 必填）后再 persist_plan。
