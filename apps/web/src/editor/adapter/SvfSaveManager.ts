/**
 * SVF 持久化 SaveManager：debounce PATCH edit-timeline，替代 Classic IndexedDB。
 */

import type { EditTimelineData } from "../../edit/types";
import { saveToSvf, type ClassicProjectJson } from "./svfProjectAdapter";

export type SvfSaveFn = (timeline: EditTimelineData) => Promise<void>;

/** 监听 Classic 项目变更并写回 SVF API。 */
export class SvfSaveManager {
  private debounceMs: number;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private isSaving = false;
  private pending: EditTimelineData | null = null;
  private baseTimeline: EditTimelineData;
  private saveFn: SvfSaveFn;

  constructor(options: {
    baseTimeline: EditTimelineData;
    saveFn: SvfSaveFn;
    debounceMs?: number;
  }) {
    this.baseTimeline = options.baseTimeline;
    this.saveFn = options.saveFn;
    this.debounceMs = options.debounceMs ?? 800;
  }

  /** 更新基准 revision 元数据（PATCH 成功后调用）。 */
  updateBase(timeline: EditTimelineData) {
    this.baseTimeline = timeline;
  }

  /** Classic 项目变更后调度保存。 */
  scheduleFromClassic(project: ClassicProjectJson) {
    const next = saveToSvf(project, this.baseTimeline);
    this.pending = next;
    this.queue();
  }

  /** 直接调度 SVF 时间轴保存。 */
  schedule(timeline: EditTimelineData) {
    this.pending = timeline;
    this.queue();
  }

  /** 立即 flush 待保存数据。 */
  async flush(): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    await this.saveNow();
  }

  getIsDirty(): boolean {
    return !!this.pending || this.isSaving;
  }

  private queue() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.saveNow(), this.debounceMs);
  }

  private async saveNow() {
    if (this.isSaving || !this.pending) return;
    this.isSaving = true;
    const toSave = this.pending;
    this.pending = null;
    try {
      await this.saveFn(toSave);
      this.baseTimeline = toSave;
    } finally {
      this.isSaving = false;
      if (this.pending) this.queue();
    }
  }
}
