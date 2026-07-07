/** Ken Burns 运镜插值（与后端 motion_detail 语义对齐） */

export interface KenBurnsState {
  scale: number;
  offsetX: number;
  offsetY: number;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function interpolateKenBurns(
  progress: number,
  motion: string | undefined,
  detail?: Record<string, unknown>
): KenBurnsState {
  const t = Math.max(0, Math.min(1, progress));
  const fromFocal = Array.isArray(detail?.from_focal) ? detail.from_focal : [0.5, 0.5];
  const toFocal = Array.isArray(detail?.to_focal) ? detail.to_focal : [0.5, 0.5];
  const scaleFrom = typeof detail?.scale_from === "number" ? detail.scale_from : 1;
  const scaleTo = typeof detail?.scale_to === "number" ? detail.scale_to : 1.15;

  let sf = scaleFrom;
  let st = scaleTo;
  if (motion === "ken_burns_out") {
    sf = 1.15;
    st = 1;
  } else if (motion === "static") {
    sf = 1;
    st = 1;
  }

  const scale = lerp(sf, st, t);
  const fx = lerp(Number(fromFocal[0] ?? 0.5), Number(toFocal[0] ?? 0.5), t);
  const fy = lerp(Number(fromFocal[1] ?? 0.5), Number(toFocal[1] ?? 0.5), t);
  return {
    scale,
    offsetX: (0.5 - fx) * 100 * (scale - 1),
    offsetY: (0.5 - fy) * 100 * (scale - 1),
  };
}
