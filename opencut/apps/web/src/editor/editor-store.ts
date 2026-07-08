/** Zustand 编辑器状态管理 */

import { create } from "zustand";
import type { EditorClip, EditorTimeline, MediaAsset, ClipTransform } from "./types";
import { emptyTimeline, defaultTransform } from "./types";

interface EditorState {
  timeline: EditorTimeline;
  mediaAssets: MediaAsset[];
  selectedClipId: string | null;
  playheadMs: number;
  isPlaying: boolean;
  isReady: boolean;

  // 时间轴操作
  setTimeline: (tl: EditorTimeline) => void;
  addClip: (layerId: string, clip: EditorClip) => void;
  updateClip: (layerId: string, clipId: string, patch: Partial<EditorClip>) => void;
  removeClip: (layerId: string, clipId: string) => void;

  // 选中状态
  setSelectedClipId: (id: string | null) => void;

  // 播放头
  setPlayheadMs: (ms: number) => void;
  setPlaying: (p: boolean) => void;
  togglePlay: () => void;

  // 媒体资产
  setMediaAssets: (assets: MediaAsset[]) => void;

  // 就绪状态
  setReady: (r: boolean) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  timeline: emptyTimeline(),
  mediaAssets: [],
  selectedClipId: null,
  playheadMs: 0,
  isPlaying: false,
  isReady: false,

  setTimeline: (tl) => set({ timeline: tl }),

  addClip: (layerId, clip) =>
    set((s) => {
      const layers = s.timeline.videoLayers.map((layer) =>
        layer.id === layerId
          ? { ...layer, clips: [...layer.clips, clip] }
          : layer,
      );
      const maxEnd = Math.max(
        s.timeline.durationMs,
        ...layers.flatMap((l) => l.clips.map((c) => c.endMs)),
      );
      return {
        timeline: {
          ...s.timeline,
          videoLayers: layers,
          durationMs: maxEnd,
        },
      };
    }),

  updateClip: (layerId, clipId, patch) =>
    set((s) => ({
      timeline: {
        ...s.timeline,
        videoLayers: s.timeline.videoLayers.map((layer) =>
          layer.id === layerId
            ? {
                ...layer,
                clips: layer.clips.map((c) =>
                  c.id === clipId ? { ...c, ...patch } : c,
                ),
              }
            : layer,
        ),
      },
    })),

  removeClip: (layerId, clipId) =>
    set((s) => ({
      timeline: {
        ...s.timeline,
        videoLayers: s.timeline.videoLayers.map((layer) =>
          layer.id === layerId
            ? { ...layer, clips: layer.clips.filter((c) => c.id !== clipId) }
            : layer,
        ),
      },
      selectedClipId: s.selectedClipId === clipId ? null : s.selectedClipId,
    })),

  setSelectedClipId: (id) => set({ selectedClipId: id }),
  setPlayheadMs: (ms) => set({ playheadMs: ms }),
  setPlaying: (p) => set({ isPlaying: p }),
  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),

  setMediaAssets: (assets) => set({ mediaAssets: assets }),
  setReady: (r) => set({ isReady: r }),
}));
