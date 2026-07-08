# 动态图文分镜补充
- load_context → create_shots → create_frames → persist_plan → finish。
- create_frames 的 element_refs 须引用已存在且已生图的 character/prop/scene 文字资产 ID。
- 禁止将 character/prop 绿幕图直接作为 shot 成片图；成片由 frame 图生图合成。
