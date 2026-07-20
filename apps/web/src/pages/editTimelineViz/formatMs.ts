/** 将毫秒格式化为 m:ss，供时间轴 ruler 与 clip 标签使用。 */
export function formatMs(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** 将毫秒格式化为 m:ss.s（细粒度）。 */
export function formatMsPrecise(ms: number): string {
  const totalSec = Math.max(0, ms) / 1000;
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  const secStr = seconds.toFixed(1);
  const paddedSec = secStr.length >= 4 ? secStr : secStr.padStart(4, "0");
  return `${minutes}:${paddedSec}`;
}
