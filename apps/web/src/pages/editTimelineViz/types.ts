/** EditTimeline 可视化页 API 响应类型（只读调试）。 */

import type { EditTimelineData } from "../../edit/types";

/** validate API 响应。 */
export interface EditTimelineValidateResponse {
  ready?: boolean;
  warnings?: string[];
  timeline_id?: string;
  revision?: number;
  validation?: {
    ready?: boolean;
    missing_items?: Array<Record<string, unknown>>;
    stats?: Record<string, unknown>;
  };
}

/** analyze API 响应。 */
export interface EditTimelineAnalyzeResponse {
  range?: { start_ms?: number; end_ms?: number };
  clips_in_range?: Array<Record<string, unknown>>;
  gaps?: Array<Record<string, unknown>>;
  overlaps?: Array<Record<string, unknown>>;
  warnings?: string[];
  missing_assets?: Array<Record<string, unknown>>;
  shot_alignment?: Array<Record<string, unknown>>;
  optimization_hints?: Array<Record<string, unknown>>;
}

export type { EditTimelineData };

/** 分析时间窗筛选参数。 */
export interface AnalyzeRangeFilter {
  start_ms?: number;
  end_ms?: number;
}
