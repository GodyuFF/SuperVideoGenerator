# 子 Agent 职责表（主编排规划参考）

> 主编排每轮结合 `user_message`、`pipeline_progress`、本表与 `delegate_agent` 工具 description 选择 **一个** agent_id / `tool_*` / `finish`。局部请求可跳步（只要生图则仅 `image_agent`；续跑剪辑则跳至 `editing_agent`）。**完整成片**时须遵守 role 中的 canonical 顺序：`storyboard_refine_agent` 为 **剪辑前最后一步**；AI 视频 / 画面图生视频模式下 `video_agent` 必须在复核之前。

> **画面图生视频（frame_i2v）完整成片 canonical**：`storyboard`（create_frames + create_video_clips）→ `image_gen`（实体 + frame）→ `video_gen`（以 frame 为唯一图生源 I2V）→ `tts_gen` → `storyboard_refine_agent` → `editing_agent`。

## script_agent

| 项 | 说明 |
|----|------|
| 职责 | 解析创意、生成剧本 Markdown、创建/更新剧情/角色/道具/场景**共享**文字资产 |
| 不做 | 创建 frame/video_clip、镜内关联、生图、分镜、配音、剪辑、成片 |
| 依赖 | 用户创意；可选已有剧本正文 |
| 产出 | Script.content_md、TextAsset（plot/character/scene/prop） |
| 何时委派 | 新建视频、改剧本、生图失败需改提示词/敏感词 |
| 上游缺失 | `return_to_master` reason=needs_user_input，请用户补充创意或约束 |

## image_agent

| 项 | 说明 |
|----|------|
| 职责 | 扫描待生图文字资产，批量 AI 生图或搜索配图并落盘；**画面图生视频**须两阶段完成 entity + 全部 frame 后再 video_gen |
| 不做 | 写剧本、分镜、TTS、剪辑 |
| 依赖 | 文字资产（character/prop/scene/frame）；**可先于或后于** storyboard（entity 与 frame 两批） |
| 产出 | MediaAsset(IMAGE)、primary_media_id、变体 media_id |
| 何时委派 | 用户要配图、剪辑缺图、分镜前补角色/场景图或分镜后补 frame 图 |
| 上游缺失 | `return_to_master` → 建议 `script_agent` 或 `storyboard_agent`（缺 frame 时） |

## storyboard_agent

| 项 | 说明 |
|----|------|
| 职责 | 生成分镜 VideoPlan；**决定镜内 element_refs**；故事书 create_frames / AI 视频 create_video_clips / **画面图生视频二者皆需** |
| 不做 | 写剧本共享资产、生图 mp4、配音、剪辑成片 |
| 依赖 | script_agent 产出的 character/scene/prop/plot |
| 产出 | VideoPlan、frame 或 video_clip 文字资产及与子镜的关联边 |
| 何时委派 | 用户要分镜、video_agent 缺 video_clip、剪辑前无 VideoPlan |
| 上游缺失 | `return_to_master` → `script_agent` |

## tts_agent

| 项 | 说明 |
|----|------|
| 职责 | 从分镜/剧本提取旁白并合成配音音频 |
| 不做 | 改剧本结构、生图、剪辑计划 |
| 依赖 | VideoPlan 或剧本旁白文本 |
| 产出 | MediaAsset(AUDIO)、按 shot 绑定到镜内 voice clip；系统自动 `sync_plan_from_tts` 对齐时长与字幕 |
| 何时委派 | 用户要配音、剪辑前缺 audio |
| 上游缺失 | `return_to_master` → `storyboard_agent` 或 `script_agent` |
| 看板 | synthesize 后自动 `sync_plan_from_tts`；幕级全片时间由系统计算，非 LLM 填写 |

## storyboard_refine_agent

| 项 | 说明 |
|----|------|
| 职责 | 分镜复核：对比规划与实测时长/配图（及 AI 视频实测），可结构性重排镜头，完善展示说明与运镜 |
| 不做 | 重新设计镜头列表、全量生图、生成 mp4、剪辑成片 |
| 依赖 | VideoPlan、配图、TTS audio；**AI 视频模式另须 video_agent 已回填视频 media** |
| 产出 | Shot.review_note、detail_revision、镜内轨道实测对齐 |
| 何时委派 | **剪辑前最后一步**：TTS（及 AI 视频模式下 video）完成后、`editing_agent` 之前；用户要求完善分镜详设 |
| 上游缺失 | `return_to_master` → `tts_agent` / `image_agent` /（ai_video）`video_agent` |
| need_regen | refine / av_sync 结果含需补图或音画大偏差镜头时，由主编排决定委派 `image_agent` / `video_agent` / `tts_agent` / `storyboard_refine_agent` |
| analyze_av_sync | TTS/视频回填后可选：分层协调（Tier0 通过 / Tier1 自动倍速·定格 / Tier2 用户选方案 / Tier3 结构化 regen_reason 打回） |
| sync_policy | 按镜主轨：`narration_master`（默认旁白）/ `visual_master`（口型·表演）/ `balanced` |
| 顺序禁忌 | **禁止**在复核之后再委派 `video_agent`；`remaining_plan` 中复核须紧挨剪辑之前 |

## video_agent

| 项 | 说明 |
|----|------|
| 职责 | AI 视频 / 画面图生视频：scan + generate_video_clips；**frame_i2v 以子镜 frame 为唯一 I2V 输入，video_clip 仅承载 motion prompt** |
| 不做 | 创建 video_clip、修改镜内关联、故事书 Ken Burns 路径 |
| 依赖 | storyboard_agent 产出的 VideoPlan + video_clip 文字资产；**frame_i2v 另须 frame 已配图** |
| 产出 | MediaAsset(VIDEO)、回填子镜 videos[].media_id |
| 何时委派 | style_mode=ai_video 或 frame_i2v 且 video_clip 已就绪；**须在 storyboard_refine_agent 之前** |
| 上游缺失 | `return_to_master` → `storyboard_agent`（缺 video_clip）或 `image_agent`（缺参考图） |

## editing_agent

| 项 | 说明 |
|----|------|
| 职责 | 规划 EditTimeline（三轨+多层）、校验素材；成片由用户在 OpenCut 导出 |
| 不做 | 生图、写剧本、改 VideoPlan 结构（可 merge 用户时间轴） |
| 依赖 | **须先完成** `storyboard_refine_agent`；另需 VideoPlan、配图/视频 media、TTS audio |
| 产出 | EditTimeline（用户侧导出成片） |
| 何时委派 | 用户要剪辑/合成/导出成片；`ready_for_edit_compose=true` 可跳步；**紧接在分镜复核之后** |
| 上游缺失 | `return_to_master` 或 `report_missing_assets` → 按 suggested_upstream 回补 |

## return_to_master 协议

子 Agent 信息不足或需主编排协调时调用 `return_to_master`（**勿**用 `finish` 冒充成功）：

- `missing_upstream`：缺上游素材/实体
- `needs_user_input`：需用户确认（交互模式下主编排可 `ask_user_question`）
- `blocked`：外部 API/配置阻塞
- `partial_done`：部分完成，需主编排决策是否继续

主编排收到后：步骤 `paused`，不记入 `completed_step_types`；补数据后 **重新委派** 同一 agent_id（子会话已清空）。
