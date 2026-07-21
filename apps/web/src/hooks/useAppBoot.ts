/**
 * 应用冷启动引导：等待字体与最短展示时长后触发退场动画。
 */

import { useEffect, useState } from "react";
import { isSvfDesktop } from "../desktop/svfDesktop";

const MIN_SPLASH_MS = 1900;
const EXIT_MS = 620;
/** 桌面壳已由 splash-boot.html 展示冷启动，Web 侧仅短退场衔接。 */
const DESKTOP_EXIT_MS = 180;

export interface AppBootState {
  /** 是否仍显示启动画面（含退场过渡）。 */
  showSplash: boolean;
  /** 是否处于淡出退场阶段。 */
  exiting: boolean;
  /** 0–100 进度，用于胶片导片条。 */
  progress: number;
}

/** 协调启动页最短停留、字体就绪与退场时序。 */
export function useAppBoot(): AppBootState {
  const [exiting, setExiting] = useState(false);
  const [done, setDone] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let raf = 0;
    let exitTimer: ReturnType<typeof setTimeout> | undefined;

    /** 桌面：Electron 已播 splash-boot，跳过二次长动画，短退场后进入主界面。 */
    if (isSvfDesktop()) {
      setProgress(100);
      setExiting(true);
      exitTimer = setTimeout(() => setDone(true), DESKTOP_EXIT_MS);
      return () => {
        if (exitTimer) clearTimeout(exitTimer);
      };
    }

    const start = performance.now();

    /** 按时间推进导片条，就绪前最高停在 94%。 */
    const tick = () => {
      const elapsed = performance.now() - start;
      const ratio = Math.min(1, elapsed / MIN_SPLASH_MS);
      setProgress(Math.min(94, ratio * 94));
      if (ratio < 1) {
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);

    const fontsReady =
      typeof document !== "undefined" && document.fonts
        ? document.fonts.ready.catch(() => undefined)
        : Promise.resolve();

    void Promise.all([fontsReady, new Promise<void>((r) => setTimeout(r, MIN_SPLASH_MS))]).then(
      () => {
        cancelAnimationFrame(raf);
        setProgress(100);
        setExiting(true);
        exitTimer = setTimeout(() => setDone(true), EXIT_MS);
      },
    );

    return () => {
      cancelAnimationFrame(raf);
      if (exitTimer) clearTimeout(exitTimer);
    };
  }, []);

  return {
    showSplash: !done,
    exiting,
    progress,
  };
}
