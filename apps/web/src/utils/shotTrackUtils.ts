/**
 * 镜内多轨 Shot 读写辅助：旁白文案、运镜、patch 体构建。
 */

import type {
  PatchVideoPlanShotBody,
  ShotAudioClip,
  ShotAudioTrack,
  ShotSubtitle,
  ShotSubShot,
  VideoPlanShot,
} from "../types/videoPlan";
import { quantizeDurationMs } from "./shotSegmentUtils";

/** 拼接镜内首条 voice clip 文案作为旁白。 */
export function shotVoiceText(shot: VideoPlanShot): string {
  for (const track of shot.audio_tracks ?? []) {
    if (track.kind !== "voice") continue;
    for (const clip of track.clips ?? []) {
      const text = (clip.text ?? "").trim();
      if (text) return text;
    }
  }
  return "";
}

/** 读取镜主画面运镜（首个 visual 或 z0 视频 clip）。 */
export function shotCameraMotion(shot: VideoPlanShot): string {
  const visual = shot.sub_shots?.[0];
  if (visual?.camera_motion) return visual.camera_motion;
  for (const track of shot.video_tracks ?? []) {
    if (track.z_index === 0 && track.clips?.[0]?.camera_motion) {
      return track.clips[0].camera_motion;
    }
  }
  return shot.camera_motion ?? "static";
}

/** 从看板 item 或 plan shot 的 audio_tracks 解析旁白文案。 */
export function resolveNarrationText(raw: Record<string, unknown>): string {
  const tracks = raw.audio_tracks as ShotAudioTrack[] | undefined;
  if (tracks?.length) {
    const shot: VideoPlanShot = { id: "", audio_tracks: tracks };
    const text = shotVoiceText(shot);
    if (text) return text;
  }
  return "";
}

/** 读取镜内元素引用（首个 visual 的 element_refs）。 */
export function shotElementRefs(
  shot: Pick<VideoPlanShot, "sub_shots">,
): Record<string, string[]> {
  return shot.sub_shots?.[0]?.element_refs ?? {};
}

/** 构造符合 create_shots / split 的最小镜 JSON。 */
export function buildMinimalShotPayload(
  order: number,
  durationMs: number,
  text: string,
  cameraMotion = "static",
): Record<string, unknown> {
  return {
    order,
    duration_ms: durationMs,
    sub_shots: [
      {
        start_ms: 0,
        end_ms: durationMs,
        description: text,
        camera_motion: cameraMotion,
      },
    ],
    audio_tracks: [
      {
        kind: "voice",
        name: "角色音",
        clips: [{ start_ms: 0, end_ms: durationMs, text }],
      },
    ],
  };
}

/** 根据表单编辑生成镜内多轨 patch 体。 */
export function buildShotPatchFromEdits(
  shot: VideoPlanShot,
  edits: {
    narration: string;
    cameraMotion: string;
    reviewNote: string;
    durationMs: number;
    elementRefs?: Record<string, string[]>;
  },
): PatchVideoPlanShotBody {
  const durationMs = Math.max(500, quantizeDurationMs(edits.durationMs));
  const sub_shots: ShotSubShot[] = [...(shot.sub_shots ?? [])];
  if (sub_shots.length === 0) {
    sub_shots.push({
      start_ms: 0,
      end_ms: durationMs,
      description: edits.narration,
      camera_motion: edits.cameraMotion,
      element_refs: edits.elementRefs ?? {},
    });
  } else {
    sub_shots[0] = {
      ...sub_shots[0],
      end_ms: durationMs,
      camera_motion: edits.cameraMotion,
      description: sub_shots[0].description || edits.narration,
      element_refs: edits.elementRefs ?? sub_shots[0].element_refs,
    };
  }

  const audioTracks: ShotAudioTrack[] = [...(shot.audio_tracks ?? [])];
  let voiceIdx = audioTracks.findIndex((t) => t.kind === "voice");
  const voiceClip: ShotAudioClip = {
    start_ms: 0,
    end_ms: durationMs,
    text: edits.narration,
    ...(voiceIdx >= 0 ? audioTracks[voiceIdx].clips?.[0] : {}),
  };
  if (voiceIdx < 0) {
    audioTracks.push({
      kind: "voice",
      name: "角色音",
      clips: [voiceClip],
    });
  } else {
    const track = audioTracks[voiceIdx];
    const clips = [...(track.clips ?? [])];
    if (clips.length === 0) clips.push(voiceClip);
    else clips[0] = { ...clips[0], ...voiceClip };
    audioTracks[voiceIdx] = { ...track, clips };
  }

  const subtitles: ShotSubtitle[] = [...(shot.subtitles ?? [])];
  if (edits.narration.trim() && subtitles.length === 0) {
    subtitles.push({ start_ms: 0, end_ms: durationMs, text: edits.narration });
  } else if (subtitles.length === 1) {
    subtitles[0] = { ...subtitles[0], text: edits.narration, end_ms: durationMs };
  }

  return {
    duration_ms: durationMs,
    review_note: edits.reviewNote.trim() || undefined,
    sub_shots,
    audio_tracks: audioTracks,
    subtitles: subtitles.length > 0 ? subtitles : undefined,
    camera_motion_refined: edits.cameraMotion,
  };
}
