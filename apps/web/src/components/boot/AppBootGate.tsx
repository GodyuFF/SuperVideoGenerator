/**
 * 启动门闸：冷启动时展示加载页，就绪后渲染子树并移除 HTML 内联占位。
 */

import { useEffect, type ReactNode } from "react";
import { AppSplashScreen } from "./AppSplashScreen";
import { useAppBoot } from "../../hooks/useAppBoot";

export interface AppBootGateProps {
  children: ReactNode;
}

/** 在应用就绪前覆盖全屏启动动画，完成后仅渲染子节点。 */
export function AppBootGate({ children }: AppBootGateProps) {
  const { showSplash, exiting, progress } = useAppBoot();

  useEffect(() => {
    /** React 启动页绘制后再移除 HTML 占位，避免首帧闪跳。 */
    const removeInline = () => {
      const inline = document.getElementById("svf-inline-boot");
      if (inline) inline.remove();
    };
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(removeInline);
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <>
      {showSplash ? <AppSplashScreen exiting={exiting} progress={progress} /> : null}
      {children}
    </>
  );
}
