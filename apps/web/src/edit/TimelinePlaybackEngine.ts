/** 时间轴播放引擎：播放头 + 当前活跃 clip */

import type { EditTimelineData, TrackClip } from "./types";

export type PlaybackListener = (playheadMs: number, playing: boolean) => void;

export class TimelinePlaybackEngine {
  private playheadMs = 0;
  private playing = false;
  private rafId = 0;
  private lastTs = 0;
  private timeline: EditTimelineData | null = null;
  private listeners = new Set<PlaybackListener>();

  setTimeline(timeline: EditTimelineData | null) {
    this.timeline = timeline;
    if (timeline && this.playheadMs > timeline.duration_ms) {
      this.playheadMs = 0;
    }
    this.emit();
  }

  getPlayhead(): number {
    return this.playheadMs;
  }

  isPlaying(): boolean {
    return this.playing;
  }

  subscribe(fn: PlaybackListener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit() {
    for (const fn of this.listeners) {
      fn(this.playheadMs, this.playing);
    }
  }

  seek(ms: number) {
    const max = this.timeline?.duration_ms ?? 0;
    this.playheadMs = Math.max(0, Math.min(ms, max));
    this.emit();
  }

  play() {
    if (!this.timeline || this.timeline.duration_ms <= 0) return;
    this.playing = true;
    this.lastTs = performance.now();
    this.tick();
    this.emit();
  }

  pause() {
    this.playing = false;
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.emit();
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  private tick = () => {
    if (!this.playing || !this.timeline) return;
    const now = performance.now();
    const delta = now - this.lastTs;
    this.lastTs = now;
    this.playheadMs += delta;
    if (this.playheadMs >= this.timeline.duration_ms) {
      this.playheadMs = this.timeline.duration_ms;
      this.playing = false;
    }
    this.emit();
    if (this.playing) {
      this.rafId = requestAnimationFrame(this.tick);
    }
  };

  activeClipsAt(ms: number): Record<string, TrackClip | null> {
    const out: Record<string, TrackClip | null> = {
      video: null,
      audio: null,
      subtitle: null,
    };
    if (!this.timeline) return out;
    for (const key of ["audio", "subtitle"] as const) {
      const clips = this.timeline.tracks[key] ?? [];
      out[key] =
        clips.find((c) => {
          const start = Number(c.start_ms ?? 0);
          const end = Number(c.end_ms ?? start + 1);
          return ms >= start && ms < end;
        }) ?? null;
    }
    const layers = this.timeline.video_layers ?? [];
    if (layers.length > 0) {
      for (const layer of [...layers].sort((a, b) => (a.z_index ?? 0) - (b.z_index ?? 0))) {
        const hit =
          (layer.clips ?? []).find((c) => {
            const start = Number(c.start_ms ?? 0);
            const end = Number(c.end_ms ?? start + 1);
            return ms >= start && ms < end;
          }) ?? null;
        if (hit) out.video = hit;
      }
    } else {
      const clips = this.timeline.tracks.video ?? [];
      out.video =
        clips.find((c) => {
          const start = Number(c.start_ms ?? 0);
          const end = Number(c.end_ms ?? start + 1);
          return ms >= start && ms < end;
        }) ?? null;
    }
    return out;
  }

  activeVideoLayersAt(ms: number): Array<{ layer: import("./types").VideoLayer; clip: TrackClip }> {
    const result: Array<{ layer: import("./types").VideoLayer; clip: TrackClip }> = [];
    if (!this.timeline) return result;
    const layers = this.timeline.video_layers ?? [];
    const sorted = [...layers].sort((a, b) => (a.z_index ?? 0) - (b.z_index ?? 0));
    for (const layer of sorted) {
      const hit =
        (layer.clips ?? []).find((c) => {
          const start = Number(c.start_ms ?? 0);
          const end = Number(c.end_ms ?? start + 1);
          return ms >= start && ms < end;
        }) ?? null;
      if (hit) result.push({ layer, clip: hit });
    }
    if (result.length === 0 && !layers.length) {
      const clip = this.activeClipsAt(ms).video;
      if (clip) result.push({ layer: { id: "legacy", z_index: 0 }, clip });
    }
    return result;
  }
}
