/**
 * 右侧抽屉左缘拖拽手柄（暗房胶片取景器风格）。
 */

interface ResizableDrawerEdgeProps {
  /** pointerdown 由 useResizableDrawerWidth 提供。 */
  onPointerDown: (e: React.PointerEvent<HTMLElement>) => void;
  /** 无障碍标签。 */
  label: string;
}

/** 右侧抽屉左缘宽度调节条。 */
export function ResizableDrawerEdge({ onPointerDown, label }: ResizableDrawerEdgeProps) {
  return (
    <div
      className="svf-drawer-resize-edge"
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") e.preventDefault();
      }}
    />
  );
}
