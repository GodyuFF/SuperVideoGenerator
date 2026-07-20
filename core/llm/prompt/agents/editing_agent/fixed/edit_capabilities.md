# 剪辑渲染能力（与 core/edit/capabilities.json 同步）

本表是 **Edit Studio / 剪辑助手浏览器导出** 已实现的能力；`plan_edit_timeline` 中字段须落在此范围内，否则 `validate_edit_assets` 会报错。

## 运镜 preset（motion / motion_detail.type）

| 值 | 效果 |
|----|------|
| `ken_burns_in` | 推入（默认） |
| `ken_burns_out` | 拉出 |
| `ken_burns_pan` | 平移 |
| `pan_right` | 向右平移 |
| `static` | 轻微静态缩放 |

别名（写入时会被归一化为 canonical preset）：

| 别名 | 映射 |
|------|------|
| `fade`, `fade_in`, `ken_burns`, `push_in`, `gentle_push_in`, `slow_zoom_in`, `zoom_in` | `ken_burns_in` |
| `pull_out`, `gentle_pull_out`, `slow_zoom_out`, `zoom_out` | `ken_burns_out` |
| `pan`, `slow_pan`, `pan_left` | `ken_burns_pan` |
| `slow_pan_right` | `pan_right` |

**禁止**自造未上表列出的运镜名（如 `gentle_drift`）；未知值会在入库/导出前回落为 `ken_burns_in`。

## motion_detail（可选，优先于 preset）

- `from_focal` / `to_focal`：归一化焦点 [x, y]，范围 0–1
- `scale_from` / `scale_to`：片内运镜缩放起止（建议 0.5–3.0）

## transform（画布缩放/位移）

- `width` / `height`：归一化 0–1，**1.0=全屏**，**0.25–0.4=画中画**
- `x` / `y`：中心点 0–1（默认 0.5, 0.5）
- 与 `motion_detail` 运镜缩放**叠加**；用户手调 scale 受 `user_locked` 保护

## 转场（transition_in / transition_out）

| type | 说明 |
|------|------|
| `cut` | 硬切（duration_ms 可为 0） |
| `fade` | 淡入/淡出 |
| `dissolve` | 交叉淡化（导出 P2） |

`duration_ms` 上限 **2000ms**。

## 背景（background）

| type | 说明 |
|------|------|
| `solid` | 纯色底，`color` 默认 `#0f172a` |
| `image` | 背景图，须 `asset_ref` 指向可访问 image media |
| `blur` | 对前景图模糊铺底（预览简化） |

## 轨道

- **video_layers**：最多 **5** 层（`max_video_layers=5`）；主画面 `z_index=0`，画中画/贴纸更高层
- **同层 clip 时间不得重叠**（导出前校验会 warning）；多角色同时出现须各占一层
- **video**：每段须可解析图片/视频（asset_ref 或 source_refs），须含 **transform**
- **audio**：TTS media
- **subtitle**：label 与 narration 对齐；后端可从 TTS subtitle_cues 自动生成；**样式须遵循成片分辨率推荐**（见下节）

## 字幕样式（按成片分辨率）

`load_edit_context` 返回 `subtitle_style_context`，含当前 `output_canvas` 与 `subtitle_style` 推荐值。规划 subtitle 轨时**必须**遵守：

| 成片尺寸 | 方向 | 推荐字号 | 底边距 | 对齐 | 单行汉字上限 |
|----------|------|----------|--------|------|--------------|
| 1920×1080 | 横屏 | ≈42px（高 3.9%） | ≈8%（≈86px） | **底部居中** | 18 |
| 1080×1920 | 竖屏 | ≈48px（高 4.4%） | ≈10%（≈108px） | **底部居中** | 14 |
| 1280×720 | 横屏 | ≈28px（高 3.9%） | ≈8%（≈58px） | **底部居中** | 18 |

**禁止**将字幕放在画面垂直正中（那是标题位，不是字幕位）。过长旁白按句拆成多条 subtitle clip，每条 `label` 不超过推荐字数。

OpenCut 预览/导出使用 `subtitle_style.opencut`（`font_size_units`、`margin_vertical_ratio`、`vertical_align=bottom`）；遗留 FFmpeg 烧录使用 `subtitle_style.ass`（`alignment=2` 底中、`font_size_px`、`margin_v_px`）。单源公式：`core/edit/subtitle_style.py`。

## 成片导出

**最终 MP4 仅由用户在剪辑助手（OpenCut 编辑器）顶栏「导出」经浏览器渲染生成**；Agent 禁止调用 `compose_final` / `export_timeline`。
服务端 FFmpeg 合成默认关闭（`SVG_EXPORT_ENABLED=1` 可恢复遗留路径）。多层 clip 在浏览器导出时按 transform 叠加（与预览一致）。
