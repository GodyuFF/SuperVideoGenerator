/**
 * 右侧抽屉宽度：左缘拖拽调宽，localStorage 记忆，视口变化时自动夹紧。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const MOBILE_MAX = 768;

export interface ResizableDrawerWidthOptions {
  /** localStorage 键名。 */
  storageKey: string;
  /** 默认宽度（px）。 */
  defaultWidth: number;
  /** 最小宽度（px）。 */
  minWidth: number;
  /** 相对视口最大宽度比例，默认 0.92。 */
  maxWidthRatio?: number;
}

function readStoredWidth(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

function persistWidth(key: string, width: number): void {
  try {
    localStorage.setItem(key, String(Math.round(width)));
  } catch {
    /* ignore quota */
  }
}

function viewportMaxWidth(ratio: number): number {
  if (typeof window === "undefined") return 920;
  return Math.floor(window.innerWidth * ratio);
}

function clampWidth(width: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, width));
}

/** 管理右侧抽屉可拖拽宽度与左缘手柄事件。 */
export function useResizableDrawerWidth({
  storageKey,
  defaultWidth,
  minWidth,
  maxWidthRatio = 0.92,
}: ResizableDrawerWidthOptions) {
  const [viewportWidth, setViewportWidth] = useState(
    () => (typeof window !== "undefined" ? window.innerWidth : 1280),
  );
  const isResizable = viewportWidth > MOBILE_MAX;

  const bounds = useMemo(() => {
    const max = viewportMaxWidth(maxWidthRatio);
    const min = Math.min(minWidth, max);
    return { min, max };
  }, [minWidth, maxWidthRatio, viewportWidth]);

  const [width, setWidth] = useState(() => {
    const stored = readStoredWidth(storageKey);
    const initial = stored ?? defaultWidth;
    return clampWidth(initial, bounds.min, bounds.max);
  });

  const widthRef = useRef(width);
  widthRef.current = width;

  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    setWidth((prev) => clampWidth(prev, bounds.min, bounds.max));
  }, [bounds.min, bounds.max]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!isResizable) return;
      e.preventDefault();
      e.stopPropagation();
      const handle = e.currentTarget;
      handle.setPointerCapture(e.pointerId);

      const startX = e.clientX;
      const startWidth = widthRef.current;
      document.body.classList.add("svf-drawer-resizing");

      const onMove = (ev: PointerEvent) => {
        const delta = startX - ev.clientX;
        const next = clampWidth(startWidth + delta, bounds.min, bounds.max);
        setWidth(next);
      };

      const onUp = (ev: PointerEvent) => {
        handle.releasePointerCapture(ev.pointerId);
        document.body.classList.remove("svf-drawer-resizing");
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        persistWidth(storageKey, widthRef.current);
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [bounds.min, bounds.max, isResizable, storageKey],
  );

  return {
    isResizable,
    widthPx: isResizable ? width : undefined,
    drawerStyle: isResizable
      ? ({ width: `${width}px`, maxWidth: "100%" } as const)
      : undefined,
    onResizePointerDown: onPointerDown,
  };
}
