# 子 Agent 职责表（主编排规划参考）

> 主编排每轮结合 `user_message`、`pipeline_progress` 与本表选择 **一个** `delegate_*` / `tool_*` / `finish`。非固定顺序：用户只要生图则仅 `delegate_image_gen`；续跑剪辑则跳至 `delegate_edit_compose`。

## script_agent（delegate_script_design）

| 项 | 说明 |
|----|------|
| 职责 | 解析创意、生成剧本 Markdown、创建/更新剧情/角色/道具/场景文字资产 |
| 不做 | 生图、分镜、配音、剪辑、成片 |
| 依赖 | 用户创意；可选已有剧本正文 |
| 产出 | Script.content_md、TextAsset（plot/character/scene/prop） |
| 何时委派 | 新建视频、改剧本、生图失败需改提示词/敏感词 |
| 上游缺失 | `return_to_master` reason=needs_user_input，请用户补充创意或约束 |

## image_agent（delegate_image_gen）

| 项 | 说明 |
|----|------|
| 职责 | 扫描待生图文字资产，批量 AI 生图或搜索配图并落盘 |
| 不做 | 写剧本、分镜、TTS、剪辑 |
| 依赖 | 文字资产（character/prop/scene）及 image_prompt |
| 产出 | MediaAsset(IMAGE)、primary_media_id、变体 media_id |
| 何时委派 | 用户要配图、分镜前需图、剪辑缺图 |
| 上游缺失 | `return_to_master` → 建议 `delegate_script_design` |

## storyboard_agent（delegate_storyboard）

| 项 | 说明 |
|----|------|
| 职责 | 生成分镜列表与 VideoPlan（镜头时长、运镜、旁白、资产引用） |
| 不做 | 生图、配音、剪辑成片 |
| 依赖 | 剧本与图文资产；配图可选但推荐已有 |
| 产出 | VideoPlan（shots[]） |
| 何时委派 | 用户要分镜、剪辑前无 VideoPlan |
| 上游缺失 | `return_to_master` → `delegate_script_design` 或 `delegate_image_gen` |

## tts_agent（delegate_tts_gen）

| 项 | 说明 |
|----|------|
| 职责 | 从分镜/剧本提取旁白并合成配音音频 |
| 不做 | 改剧本结构、生图、剪辑计划 |
| 依赖 | VideoPlan 或剧本旁白文本 |
| 产出 | MediaAsset(AUDIO)、按 shot 绑定的配音 |
| 何时委派 | 用户要配音、剪辑前缺 audio |
| 上游缺失 | `return_to_master` → `delegate_storyboard` 或 `delegate_script_design` |

## video_agent（delegate_video_gen）

| 项 | 说明 |
|----|------|
| 职责 | AI 视频模式：按镜头调用视频生成 API |
| 不做 | 动态图文模式的图片 Ken Burns 路径 |
| 依赖 | VideoPlan、可选镜头参考图 |
| 产出 | MediaAsset(VIDEO) |
| 何时委派 | style_mode=ai_video 且用户要视频片段 |
| 上游缺失 | `return_to_master` → `delegate_storyboard` |

## editing_agent（delegate_edit_compose）

| 项 | 说明 |
|----|------|
| 职责 | 规划 EditTimeline（三轨+多层）、校验素材、FFmpeg 合成成片 |
| 不做 | 生图、写剧本、改 VideoPlan 结构（可 merge 用户时间轴） |
| 依赖 | VideoPlan、配图 media、TTS audio；TTS 之后执行 |
| 产出 | EditTimeline、MediaAsset(FINAL) mp4 |
| 何时委派 | 用户要剪辑/合成/导出成片；`ready_for_edit_compose=true` 可跳步 |
| 上游缺失 | `return_to_master` 或 `report_missing_assets` → 按 suggested_upstream 回补 |

## return_to_master 协议

子 Agent 信息不足或需主编排协调时调用 `return_to_master`（**勿**用 `finish` 冒充成功）：

- `missing_upstream`：缺上游素材/实体
- `needs_user_input`：需用户确认（交互模式下主编排可 `ask_user_question`）
- `blocked`：外部 API/配置阻塞
- `partial_done`：部分完成，需主编排决策是否继续

主编排收到后：步骤 `paused`，不记入 `completed_step_types`；补数据后 **重新委派** 同一子 Agent（子会话已清空）。
