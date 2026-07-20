/**
 * 从已绑定配音音频拉取句级字幕预览（服务端 TTS cues / WhisperX ASR）。
 */

const API = "/api";

/** 服务端返回的单条字幕。 */
export interface VoiceAudioSubtitleRow {
  id?: string;
  text?: string;
  start_ms?: number;
  end_ms?: number;
  character?: string;
  color?: string;
}

/** 调用 subtitles-from-voice，得到相对镜起点的句级字幕列表。 */
export async function fetchSubtitlesFromVoiceAudio(
  projectId: string,
  scriptId: string,
  shotId: string,
): Promise<VoiceAudioSubtitleRow[]> {
  const res = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/shots/${shotId}/subtitles-from-voice`,
    { method: "POST" },
  );
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `HTTP ${res.status}`);
  }
  const data = (await res.json()) as { subtitles?: VoiceAudioSubtitleRow[] };
  return Array.isArray(data.subtitles) ? data.subtitles : [];
}
