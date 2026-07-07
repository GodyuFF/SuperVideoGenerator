import type { TrackClip } from "./types";

const MOTION_ABBR: Record<string, string> = {
  ken_burns_in: "KB+",
  ken_burns_out: "KB-",
  ken_burns_pan: "KBP",
  pan_right: "PAN",
  static: "ST",
};

const TRANSITION_ABBR: Record<string, string> = {
  fade: "F",
  dissolve: "D",
  cut: "",
};

export function motionBadge(motion?: string): string {
  if (!motion || motion === "static") return "";
  return MOTION_ABBR[motion] ?? motion.slice(0, 3).toUpperCase();
}

export function transitionBadge(type?: string): string {
  if (!type || type === "cut") return "";
  return TRANSITION_ABBR[type] ?? type.slice(0, 1).toUpperCase();
}

export function clipBadgeSummary(clip: TrackClip): string[] {
  const badges: string[] = [];
  const kfCount = clip.transform?.keyframes?.length ?? 0;
  if (kfCount > 0) badges.push(`◇${kfCount}`);
  const motion = motionBadge(clip.motion);
  if (motion) badges.push(motion);
  const tin = transitionBadge(clip.transition_in?.type);
  const tout = transitionBadge(clip.transition_out?.type);
  if (tin) badges.push(`↓${tin}`);
  if (tout) badges.push(`↑${tout}`);
  return badges;
}

export function keyframeTooltip(kf: {
  time_ms?: number;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  opacity?: number;
  rotation?: number;
}): string {
  const parts = [`t=${kf.time_ms ?? 0}ms`];
  if (kf.x != null) parts.push(`x=${kf.x.toFixed(2)}`);
  if (kf.y != null) parts.push(`y=${kf.y.toFixed(2)}`);
  if (kf.width != null) parts.push(`w=${kf.width.toFixed(2)}`);
  if (kf.height != null) parts.push(`h=${kf.height.toFixed(2)}`);
  if (kf.opacity != null) parts.push(`α=${kf.opacity.toFixed(2)}`);
  if (kf.rotation != null) parts.push(`∠${kf.rotation.toFixed(0)}°`);
  return parts.join(" ");
}
