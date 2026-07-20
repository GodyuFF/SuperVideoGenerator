# WhisperX 字幕强制对齐设计

> 日期：2026-07-14  
> 状态：已批准并实现

## 目标

在缺少 TTS 边界 `subtitle_cues` 时，用 WhisperX 将已知旁白文案强制对齐到本地音频，生成句级 `start_ms` / `end_ms`。

## 决策

| 项 | 选择 |
|----|------|
| 触发时机 | 所有缺 cue 的音频（上传 + 无边界 TTS） |
| 依赖 | 主 `requirements.txt` 必装 `whisperx` |
| 设备 | 仅 CUDA GPU；无 GPU / 失败 → 标点+字数比例 fallback |
| 接入点 | `build_cues_for_audio_media` |
| 对齐方式 | 已知文本 `whisperx.align`（不依赖转写） |

## 流程

```
metadata.subtitle_cues 有 → 返回
有文案 + 本地音频 + CUDA → WhisperX 强制对齐
→ 标点拆分 + 时长比例 fallback
```

## 配置

- `SVG_WHISPERX_LANGUAGE`（默认 `zh`）
- `SVG_WHISPERX_ALIGN_MODEL`（可选，覆盖默认 wav2vec2）
