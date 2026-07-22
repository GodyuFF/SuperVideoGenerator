/**
 * 执行计划步骤 outputs 的折叠摘要：按媒体 kind / 文字 label 聚合为一行文案。
 */

import type { StepOutput } from "../types";

const MEDIA_KINDS = new Set(["image", "video", "audio"]);
const TEXT_KINDS = new Set(["text", "json"]);

/** 摘要文案注入（由 i18n 提供）。 */
export type PlanOutputSummaryLabels = {
  kindImage: string;
  kindVideo: string;
  kindAudio: string;
  kindText: string;
  /** 已知类型 label → 可读名（key 小写）。 */
  labelNames: Record<string, string>;
};

/** 截断过长的唯一标题。 */
function truncateLabel(label: string, maxLen: number): string {
  const t = label.trim();
  if (t.length <= maxLen) return t;
  return `${t.slice(0, Math.max(1, maxLen - 1))}…`;
}

/** 归一化分组键：trim；已知类型词转小写以便映射。 */
function groupKey(label: string, labelNames: Record<string, string>): string {
  const raw = label.trim();
  const lower = raw.toLowerCase();
  if (lower in labelNames || /^[a-z][a-z0-9_]*$/i.test(raw)) return lower;
  return raw;
}

/**
 * 将步骤产出折叠为一行摘要；空列表返回空字符串。
 * 媒体按 kind 计数；文字/json 有重复 label 则聚合，否则 ≤3 列标题、>3 显示「文字 ×N」。
 */
export function summarizePlanOutputs(
  outputs: StepOutput[],
  labels: PlanOutputSummaryLabels,
  options?: { maxSegments?: number; maxUniqueLabelLen?: number },
): string {
  const maxSegments = options?.maxSegments ?? 4;
  const maxUniqueLabelLen = options?.maxUniqueLabelLen ?? 16;
  if (!outputs.length) return "";

  const mediaCounts = { image: 0, video: 0, audio: 0 };
  const textByLabel = new Map<string, { display: string; count: number }>();

  for (const o of outputs) {
    const kind = String(o.kind || "");
    if (MEDIA_KINDS.has(kind)) {
      mediaCounts[kind as keyof typeof mediaCounts] += 1;
      continue;
    }
    if (!TEXT_KINDS.has(kind)) continue;
    const key = groupKey(o.label || "", labels.labelNames);
    const mapped = labels.labelNames[key];
    const display = mapped ?? truncateLabel(o.label || key, maxUniqueLabelLen);
    const prev = textByLabel.get(key);
    if (prev) prev.count += 1;
    else textByLabel.set(key, { display, count: 1 });
  }

  const segments: string[] = [];
  if (mediaCounts.image) segments.push(`${labels.kindImage} ×${mediaCounts.image}`);
  if (mediaCounts.video) segments.push(`${labels.kindVideo} ×${mediaCounts.video}`);
  if (mediaCounts.audio) segments.push(`${labels.kindAudio} ×${mediaCounts.audio}`);

  const textEntries = [...textByLabel.values()];
  const textTotal = textEntries.reduce((n, e) => n + e.count, 0);
  if (textTotal > 0) {
    const hasDup = textEntries.some((e) => e.count >= 2);
    if (hasDup) {
      for (const e of textEntries) {
        segments.push(`${e.display} ×${e.count}`);
      }
    } else if (textEntries.length <= 3) {
      for (const e of textEntries) segments.push(e.display);
    } else {
      segments.push(`${labels.kindText} ×${textTotal}`);
    }
  }

  if (segments.length <= maxSegments) return segments.join(" · ");
  const head = segments.slice(0, maxSegments);
  const rest = segments.length - maxSegments;
  return `${head.join(" · ")} · +${rest}`;
}
