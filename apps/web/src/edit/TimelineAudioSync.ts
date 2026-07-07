/** 预览播放时同步 timeline audio 轨 */

import { resolveMediaPlayUrl } from "../utils/mediaUrl";
import type { TimelinePlaybackEngine } from "./TimelinePlaybackEngine";
import type { TrackClip } from "./types";

const SEEK_THRESHOLD_SEC = 0.1;

export class TimelineAudioSync {
  private audio: HTMLAudioElement;
  private currentClipId: string | null = null;
  private currentUrl = "";

  constructor() {
    this.audio = document.createElement("audio");
    this.audio.preload = "auto";
  }

  sync(
    engine: TimelinePlaybackEngine,
    playheadMs: number,
    isPlaying: boolean,
    projectId?: string | null,
    scriptId?: string | null
  ): void {
    const active = engine.activeClipsAt(playheadMs).audio as TrackClip | null;
    if (!active?.preview_url) {
      this.pauseAndClear();
      return;
    }

    const url = resolveMediaPlayUrl(active.preview_url, projectId, scriptId);
    if (!url) {
      this.pauseAndClear();
      return;
    }

    const clipId = String(active.id ?? `${active.start_ms}-${url}`);
    const startMs = Number(active.start_ms ?? 0);
    const localSec = Math.max(0, (playheadMs - startMs) / 1000);

    if (clipId !== this.currentClipId || url !== this.currentUrl) {
      this.currentClipId = clipId;
      this.currentUrl = url;
      this.audio.pause();
      this.audio.src = url;
      this.audio.load();
    }

    if (Math.abs(this.audio.currentTime - localSec) > SEEK_THRESHOLD_SEC) {
      try {
        this.audio.currentTime = localSec;
      } catch {
        /* ignore seek before metadata */
      }
    }

    if (isPlaying) {
      void this.audio.play().catch(() => {
        /* autoplay policy or load race */
      });
    } else {
      this.audio.pause();
    }
  }

  dispose(): void {
    this.pauseAndClear();
    this.audio.removeAttribute("src");
    this.audio.load();
  }

  private pauseAndClear(): void {
    this.audio.pause();
    this.currentClipId = null;
    this.currentUrl = "";
  }
}
