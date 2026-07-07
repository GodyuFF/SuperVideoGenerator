动态图文模式：
1. load_context 一次即可拿到剧本正文与配图；勿传 script_id。
2. create_shots：narration_text + camera_motion 均必填；camera_motion **仅**可使用 edit_capabilities 枚举或别名（如 ken_burns_in、fade、pan），**禁止**自造 gentle_push_in / slow_zoom_in 等名称。
3. asset_refs 用 image/character/scene/prop 键，禁止 asset_id 键；示例 `{"image":["media_xxx"]}`。
4. 勿用 read_webpage / 勿反复 get_plan。
