/**

 * 子镜 produce_mode ↔ videoGenMode 映射（对齐 core/edit/sub_shot_produce.py）。

 * 不依赖 shotSegmentUtils，避免循环导入。

 */



/** 子镜产出意图：静图视频 / 文生视频 / 图生视频。 */

export type ProduceMode = "still" | "text2video" | "img2video";



/**

 * 画面成片模式（与 shotSegmentUtils.VisualVideoGenMode 字面量一致）。

 * 独立声明以避免与 shotSegmentUtils 循环依赖。

 */

export type VisualVideoGenMode = "still" | "img2video" | "text2video" | "keyframes";



const PRODUCE_MODES: ReadonlySet<string> = new Set(["still", "text2video", "img2video"]);



const LEGACY_PRODUCE: Record<string, ProduceMode> = {

  still_edit: "still",

  ai_video: "img2video",

  hybrid: "img2video",

  keyframes: "img2video",

};



/** 将 plan 字符串规范为合法 ProduceMode；非法则 still。 */

export function normalizeProduceMode(raw: string | undefined | null): ProduceMode {

  const mode = (raw ?? "").trim();

  if (LEGACY_PRODUCE[mode]) return LEGACY_PRODUCE[mode];

  if (PRODUCE_MODES.has(mode)) return mode as ProduceMode;

  return "still";

}



/** produce_mode → 默认 videoGenMode。 */

export function produceModeToVideoGenMode(mode: ProduceMode): VisualVideoGenMode {

  return mode;

}



/** 多个 videoGenMode 汇总子镜 produce_mode（取首个合法值）。 */

export function syncProduceModeFromVideoGenModes(

  modes: VisualVideoGenMode[],

): ProduceMode {

  for (const m of modes) {

    const coerced = normalizeProduceMode(m);

    if (coerced) return coerced;

  }

  return "still";

}



/** videoGenMode → produce_mode。 */

export function videoGenModeToProduceModeHint(mode: string): ProduceMode {

  return normalizeProduceMode(mode || "still");

}



/** 是否需要展示画面挂接区。 */

export function produceModeNeedsFrame(mode: ProduceMode): boolean {

  return mode === "still" || mode === "img2video";

}



/** 是否需要展示视频挂接区。 */

export function produceModeNeedsVideo(mode: ProduceMode): boolean {

  return mode === "text2video" || mode === "img2video";

}


