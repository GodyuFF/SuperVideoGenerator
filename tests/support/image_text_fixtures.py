"""测试用图文资产 content 样例（填满 required 字段）。"""

from typing import Any


def _pad_description(text: str, min_len: int = 80) -> str:
    if len(text) >= min_len:
        return text
    return text + "。" + "细节描写用于 AI 生图测试。" * ((min_len - len(text)) // 8 + 1)


def character_content(**overrides: Any) -> dict[str, Any]:
    base = {
        "summary": "测试角色",
        "description": _pad_description(
            "年轻女性，黑色短发，穿都市休闲装，站在霓虹灯下的街道，神情专注。"
        ),
        "prompt_hint": "柔和侧光，浅景深，电影感构图",
        "visual_style": "写实插画",
        "color_palette": "暖色霓虹与冷色阴影对比",
        "role": "主角",
        "personality": "坚韧",
        "age_range": "25-30",
        "gender": "女",
        "costume": "休闲夹克与牛仔裤",
        "distinctive_features": "左耳银色耳钉",
        "ethnicity": "东亚",
        "body_type": "匀称",
        "height": "中等",
        "build": "偏瘦",
        "hair_style": "短发",
        "hair_color": "黑色",
        "eye_color": "棕色",
        "facial_features": "清秀面庞",
        "default_expression": "平静",
        "default_pose": "站立",
        "accessories": "单肩包",
    }
    base.update(overrides)
    return base


def scene_content(**overrides: Any) -> dict[str, Any]:
    base = {
        "summary": "都市黄昏街道",
        "description": _pad_description(
            "现代都市黄昏街道，霓虹初上，湿润路面反射灯光，行人稀疏，远处高楼轮廓清晰。"
        ),
        "prompt_hint": "广角镜头，黄金时刻光线",
        "visual_style": "赛博朋克写实",
        "color_palette": "蓝紫与橙黄",
        "location": "城市主街",
        "time_of_day": "黄昏",
        "weather": "晴朗",
        "lighting": "霓虹与夕阳混合",
        "mood": "静谧",
        "spatial_layout": "街道纵深，两侧商铺",
        "architecture_style": "现代玻璃幕墙",
        "key_objects": "路灯、招牌",
        "foreground": "湿润路面",
        "background": "高楼天际线",
        "camera_angle": "平视略低",
        "depth_of_field": "中等景深",
        "color_tone": "冷暖对比",
    }
    base.update(overrides)
    return base


def prop_content(**overrides: Any) -> dict[str, Any]:
    base = {
        "summary": "复古相机",
        "description": _pad_description(
            "银色复古胶片相机，金属机身有轻微划痕，皮质肩带，镜头反光可见环境。"
        ),
        "prompt_hint": "产品特写，柔光箱打光",
        "visual_style": "写实产品摄影",
        "color_palette": "银灰与暖棕",
        "category": "日用品",
        "material": "金属与皮革",
        "size_scale": "手持大小",
        "usage": "摄影道具",
        "condition": "轻微使用痕迹",
        "shape": "经典单反造型",
        "color": "银色",
        "texture": "金属拉丝",
        "brand_style": "复古胶片风",
        "visual_details": "镜头环纹理清晰",
    }
    base.update(overrides)
    return base
