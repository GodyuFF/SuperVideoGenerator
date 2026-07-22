/** planOutputSummary 自测。用法：node --experimental-strip-types apps/web/src/utils/planOutputSummary.selftest.ts */

import { summarizePlanOutputs } from "./planOutputSummary.ts";
import type { StepOutput } from "../types";

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(msg);
}

function out(kind: StepOutput["kind"], label: string, i = 0): StepOutput {
  return { kind, label, asset_id: `a${i}` };
}

const labels = {
  kindImage: "图片",
  kindVideo: "视频",
  kindAudio: "音频",
  kindText: "文字",
  labelNames: {
    character: "角色",
    prop: "道具",
    scene: "场景",
    plot: "情节",
    video_plan: "视频计划",
  },
};

assert(summarizePlanOutputs([], labels) === "", "empty");

const scriptLike = [
  out("json", "character", 1),
  out("json", "character", 2),
  out("json", "character", 3),
  out("json", "prop", 4),
  out("json", "prop", 5),
  out("json", "scene", 6),
  out("json", "scene", 7),
  out("json", "scene", 8),
  out("json", "scene", 9),
  out("json", "scene", 10),
  out("json", "plot", 11),
  out("json", "plot", 12),
  out("json", "plot", 13),
  out("json", "plot", 14),
  out("json", "plot", 15),
  out("json", "plot", 16),
  out("json", "plot", 17),
  out("json", "plot", 18),
  out("json", "plot", 19),
];
assert(
  summarizePlanOutputs(scriptLike, labels) === "角色 ×3 · 道具 ×2 · 场景 ×5 · 情节 ×9",
  "aggregate duplicate labels",
);

const uniqueShort = [
  out("text", "荒漠孤影", 1),
  out("text", "刀客出场", 2),
  out("text", "刀的特写", 3),
];
assert(
  summarizePlanOutputs(uniqueShort, labels) === "荒漠孤影 · 刀客出场 · 刀的特写",
  "unique <=3 list titles",
);

const uniqueMany = Array.from({ length: 5 }, (_, i) => out("text", `镜头${i + 1}`, i));
assert(summarizePlanOutputs(uniqueMany, labels) === "文字 ×5", "unique >3 collapse");

const media = [
  out("image", "角色图", 1),
  out("image", "场景图", 2),
  out("audio", "旁白", 3),
];
assert(summarizePlanOutputs(media, labels) === "图片 ×2 · 音频 ×1", "media buckets");

const manySegs = [
  ...["a", "b", "c", "d", "e"].flatMap((L, i) => [
    out("json", L, i * 2),
    out("json", L, i * 2 + 1),
  ]),
];
assert(
  summarizePlanOutputs(manySegs, labels) === "a ×2 · b ×2 · c ×2 · d ×2 · +1",
  "max 4 segments +k",
);

assert(
  summarizePlanOutputs([out("json", "Character", 1), out("json", "character", 2)], labels) ===
    "角色 ×2",
  "normalize case for known labels",
);

console.log("planOutputSummary.selftest ok");
