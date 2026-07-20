# 音画时长协调（AV Sync）

> 更新日期：2026-07-20  
> 相关代码：`core/edit/av_sync/`、`core/edit/ffmpeg_renderer.py`、`core/edit/timeline.py`

## 1. 问题

AI 视频生成常约 5s，TTS 配音可达数秒至十余秒。分镜层已用 TTS 拉长 `Shot.duration_ms`，但剪辑/导出层曾以视频终点钳制音频，导致成片配音被截断。

## 2. 主轨策略（按镜）

| `sync_policy` | 含义 | 默认推断 |
|---------------|------|----------|
| `narration_master` | 画面适配配音 | storybook；ai_video 无角色对白 |
| `visual_master` | 配音适配画面 | `lip_sync_required=true` |
| `balanced` | 双向微调 | ai_video + 角色对白 |

字段：`Shot.sync_policy` / `lip_sync_required` / `sync_notes` / `proposed_sync_actions`。

## 3. Tier 分级

| Tier | 偏差 \|delta\| | 行为 |
|------|----------------|------|
| 0 | ≤500ms | 通过 |
| 1 | 500ms–2s | 自动：视频慢放 / 尾帧定格 / 双向变速 |
| 2 | 2s–4s | 输出 ranked 方案，UI/API 一键应用 |
| 3 | >4s 或口型且 >800ms | `need_regen` + JSON `regen_reason`，主编排委派 |

`playback_rate` 采用 **NLE 语义**：`rate<1` 慢放（时长变长），`rate>1` 加速。

偏差度量：`narration_master` 用 `tts_ms - video_ms`（有真视频时；槽位常已被 TTS 拉长，不能用 slot）；无视频素材时静图 loop 视为已对齐。

## 4. 导出语义

- 视频：`setpts=(1/rate)*PTS` + 可选 `tpad=stop_mode=clone`
- 音频：`atempo=rate`
- `narration_master`：`sync_audio` **不再**钳制音频到视频终点；`finalize_merged_timeline` 可扩展视频终点
- OpenCut：视频与音频均 `padSourceToClip`；`metadata.playback_rate` ↔ `retime.rate`

## 5. API / Tools

- `POST .../video-plan/av-sync` — `{ mode, shot_ids? }`
- `POST .../video-plan/shots/{id}/av-sync/apply` — `{ action }`
- Tool：`analyze_av_sync`；`sync_actual_assets` / TTS / 视频回填后自动 `reconcile_script_av`

## 6. 配置阈值

见 `core/edit/av_sync/types.py`：`TIER0/1/2_MAX_MS`、`VIDEO_RATE_AUTO_MAX`、`FREEZE_TAIL_AUTO_MAX_MS`、`AUDIO_RATE_*`。
