故事书模式（每子镜必须 create_frames 创建剧本画面资产）：
1. load_context 一次即可拿到剧本正文与配图；**必须传 `script_id`**（与会话编排状态 / project_context 中的 script_id 完全一致），禁止省略或凭标题猜测。
2. create_shots：`sub_shots` + `audio_tracks`（voice）均必填；多子镜时段须首尾相接且落在 `duration_ms` 内；`camera_motion` **仅** canonical（`ken_burns_in`、`ken_burns_out`、`ken_burns_pan`、`pan_right`、`static`），**禁止** `slow_zoom_in` / `slow_pan` / `gentle_push_in` 等别名。
3. voice clip `text` 为旁白全文；`duration_ms` 须覆盖朗读（约 3–4 字/秒，单镜 5–20s）；时间均为**镜内相对毫秒**，勿填全片绝对时间。
4. `sub_shots[].element_refs` 用 character/scene/prop 键；禁止 asset_id 键。
5. create_frames：`frames.length` 须等于全部子镜数量；每条 `sub_shot_id` + `image_prompt` + `element_refs` 必填（可仅传 sub_shot_id）；读返回 `frame_links`。
6. persist_plan：勿重传空 images；勿用 read_webpage / 勿反复 get_plan。
