/**
 * 应用冷启动加载页：暗房胶片取景器 + 滚动胶片条。
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

export interface AppSplashScreenProps {
  /** 是否进入淡出退场。 */
  exiting?: boolean;
  /** 导片进度 0–100。 */
  progress?: number;
}

const STATUS_KEYS = [
  "splash.statusDeveloping",
  "splash.statusLoading",
  "splash.statusCalibrating",
] as const;

const FILM_FRAME_COUNT = 9;

/** 渲染全屏启动加载动画，退场时由父级卸载。 */
export function AppSplashScreen({ exiting = false, progress = 0 }: AppSplashScreenProps) {
  const { t } = useTranslation("common");
  const [statusIndex, setStatusIndex] = useState(0);

  const statusText = t(STATUS_KEYS[statusIndex]);

  const filmFrames = useMemo(
    () =>
      Array.from({ length: FILM_FRAME_COUNT }, (_, i) => ({
        id: i,
        tone: i % 3,
      })),
    [],
  );

  useEffect(() => {
    if (exiting) return;
    const timer = setInterval(() => {
      setStatusIndex((idx) => (idx + 1) % STATUS_KEYS.length);
    }, 720);
    return () => clearInterval(timer);
  }, [exiting]);

  return (
    <div
      className={`app-splash${exiting ? " app-splash--exit" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy={!exiting}
      aria-label={statusText}
    >
      <div className="app-splash__ambient" aria-hidden />
      <div className="app-splash__sprocket" aria-hidden />

      <div className="app-splash__body">
        <p className="app-splash__eyebrow">{t("splash.eyebrow")}</p>

        <div className="app-splash__viewfinder" aria-hidden>
          <span className="app-splash__corner app-splash__corner--tl" />
          <span className="app-splash__corner app-splash__corner--tr" />
          <span className="app-splash__corner app-splash__corner--bl" />
          <span className="app-splash__corner app-splash__corner--br" />
          <div className="app-splash__film-window">
            <div className="app-splash__film-track">
              {[...filmFrames, ...filmFrames].map((frame, idx) => (
                <div
                  key={`frame-${idx}`}
                  className={`app-splash__frame app-splash__frame--tone-${frame.tone}`}
                />
              ))}
            </div>
            <div className="app-splash__scanline" />
            <div className="app-splash__grain" />
          </div>
        </div>

        <h1 className="app-splash__title">
          <span className="app-splash__brand-dot" aria-hidden />
          SuperVideoGenerator
        </h1>
        <p className="app-splash__tagline">{t("splash.tagline")}</p>
        <p className="app-splash__status" key={statusIndex}>
          {statusText}
        </p>

        <div className="app-splash__leader" aria-hidden>
          <div className="app-splash__leader-track">
            <div
              className="app-splash__leader-fill"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            />
          </div>
          <span className="app-splash__leader-mark">{Math.round(progress)}</span>
        </div>
      </div>
    </div>
  );
}
