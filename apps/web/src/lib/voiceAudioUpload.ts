/**
 * 分镜镜内配音音频上传 API。
 */

const API = "/api";

export interface VoiceAudioUploadResult {
  media_id: string;
  duration_ms: number;
  subtitle_cues?: Array<{ text: string; start_ms: number; end_ms: number }>;
  link?: string;
  sync?: {
    shot_id: string;
    media_id: string;
    duration_ms: number;
    subtitle_count: number;
  };
}

/** 上传配音音频并绑定到指定 voice clip（服务端自动同步时长与字幕）。 */
export async function uploadShotVoiceAudio(
  projectId: string,
  scriptId: string,
  shotId: string,
  file: File,
  opts: {
    clipId?: string;
    narrationText?: string;
    bindClip?: boolean;
  } = {},
): Promise<VoiceAudioUploadResult> {
  const form = new FormData();
  form.append("file", file);
  if (opts.clipId) form.append("clip_id", opts.clipId);
  if (opts.narrationText) form.append("narration_text", opts.narrationText);
  form.append("bind_clip", String(opts.bindClip !== false));

  const res = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/shots/${shotId}/voice-audio`,
    { method: "POST", body: form },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(String(body.detail ?? `上传失败 (${res.status})`));
  }
  return (await res.json()) as VoiceAudioUploadResult;
}
