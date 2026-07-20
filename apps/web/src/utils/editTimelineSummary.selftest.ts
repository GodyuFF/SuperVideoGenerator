/**
 * editTimelineSummary 纯函数自检（Node 可直接跑，无构建依赖）。
 * 用法：node --experimental-strip-types apps/web/src/utils/editTimelineSummary.selftest.ts
 * 或由 pytest 通过 subprocess 调用。
 */
import {
  buildEditTimelineStripSummary,
  shouldShowShotEditTimelineSection,
} from "./editTimelineSummary.ts";

function assert(cond: unknown, msg: string): void {
  if (!cond) throw new Error(msg);
}

assert(shouldShowShotEditTimelineSection(false) === false, "gate off");
assert(shouldShowShotEditTimelineSection(true) === true, "gate on");
assert(buildEditTimelineStripSummary(null) === null, "null timeline");
assert(
  buildEditTimelineStripSummary({ duration_ms: 0, tracks: { video: [], audio: [], subtitle: [] } }) ===
    null,
  "zero duration",
);

const summary = buildEditTimelineStripSummary({
  duration_ms: 10000,
  tracks: {
    video: [{ id: "v1", start_ms: 0, end_ms: 5000, label: "A" }],
    audio: [{ id: "a1", start_ms: 0, end_ms: 10000, label: "VO" }],
    subtitle: [],
  },
});
assert(summary !== null, "summary");
assert(summary!.durationMs === 10000, "duration");
assert(summary!.tracks.video.length === 1, "video clips");
assert(summary!.tracks.audio[0].label === "VO", "audio label");
assert(summary!.tracks.subtitle.length === 0, "empty subtitle");

console.log("editTimelineSummary.selftest: ok");
