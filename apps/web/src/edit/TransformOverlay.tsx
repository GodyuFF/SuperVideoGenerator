import { useCallback, useEffect, useRef } from "react";
import { interpolateTransform } from "./transformInterp";
import type { ClipTransform, TrackClip } from "./types";
import { DEFAULT_TRANSFORM } from "./types";

type HandleKind = "move" | "nw" | "ne" | "sw" | "se" | "rotate";

interface TransformOverlayProps {
  clip: TrackClip | null;
  playheadMs: number;
  canvasWidth: number;
  canvasHeight: number;
  editable: boolean;
  onTransformChange: (patch: Partial<ClipTransform>) => void;
}

function clamp01(v: number): number {
  return Math.max(0.02, Math.min(2, v));
}

export function TransformOverlay({
  clip,
  playheadMs,
  canvasWidth,
  canvasHeight,
  editable,
  onTransformChange,
}: TransformOverlayProps) {
  const dragRef = useRef<{
    kind: HandleKind;
    startX: number;
    startY: number;
    base: ClipTransform;
  } | null>(null);

  const localMs = clip
    ? Math.max(0, playheadMs - Number(clip.start_ms ?? 0))
    : 0;
  const tr = clip
    ? interpolateTransform(clip, localMs)
    : { x: 0.5, y: 0.5, width: 1, height: 1, opacity: 1, rotation: 0, scale: 1 };

  const drawW = canvasWidth * tr.width * tr.scale;
  const drawH = canvasHeight * tr.height * tr.scale;
  const cx = tr.x * canvasWidth;
  const cy = tr.y * canvasHeight;
  const left = cx - drawW / 2;
  const top = cy - drawH / 2;

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || !clip) return;
      const dx = (e.clientX - drag.startX) / canvasWidth;
      const dy = (e.clientY - drag.startY) / canvasHeight;
      const base = drag.base;
      const uniform = e.shiftKey;

      if (drag.kind === "move") {
        onTransformChange({
          x: clamp01((base.x ?? 0.5) + dx),
          y: clamp01((base.y ?? 0.5) + dy),
        });
        return;
      }

      if (drag.kind === "rotate") {
        const angle = Math.atan2(e.clientY - top - drawH / 2, e.clientX - left - drawW / 2);
        onTransformChange({ rotation: (angle * 180) / Math.PI + 90 });
        return;
      }

      let nw = base.width ?? 1;
      let nh = base.height ?? 1;
      let nx = base.x ?? 0.5;
      let ny = base.y ?? 0.5;

      if (drag.kind.includes("e")) nw = clamp01(nw + dx * 2);
      if (drag.kind.includes("w")) nw = clamp01(nw - dx * 2);
      if (drag.kind.includes("s")) nh = clamp01(nh + dy * 2);
      if (drag.kind.includes("n")) nh = clamp01(nh - dy * 2);

      if (uniform) {
        const avg = (nw + nh) / 2;
        nw = avg;
        nh = avg;
      }

      onTransformChange({ x: nx, y: ny, width: nw, height: nh });
    },
    [canvasHeight, canvasWidth, clip, drawH, drawW, left, onTransformChange, top]
  );

  const onPointerUp = useCallback(() => {
    dragRef.current = null;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
  }, [onPointerMove]);

  useEffect(() => () => window.removeEventListener("pointermove", onPointerMove), [onPointerMove]);

  if (!clip || clip.track !== "video" || !editable) return null;

  function startDrag(kind: HandleKind, e: React.PointerEvent) {
    e.stopPropagation();
    e.preventDefault();
    dragRef.current = {
      kind,
      startX: e.clientX,
      startY: e.clientY,
      base: { ...DEFAULT_TRANSFORM, ...clip!.transform, ...tr },
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }

  const boxStyle = {
    left: `${left}px`,
    top: `${top}px`,
    width: `${drawW}px`,
    height: `${drawH}px`,
    transform: `rotate(${tr.rotation}deg)`,
  };

  const handles: { kind: HandleKind; className: string }[] = [
    { kind: "nw", className: "edit-transform-handle-nw" },
    { kind: "ne", className: "edit-transform-handle-ne" },
    { kind: "sw", className: "edit-transform-handle-sw" },
    { kind: "se", className: "edit-transform-handle-se" },
    { kind: "rotate", className: "edit-transform-handle-rotate" },
  ];

  return (
    <div className="edit-transform-overlay" aria-hidden>
      <div className="edit-transform-box" style={boxStyle}>
        <div
          className="edit-transform-move"
          onPointerDown={(e) => startDrag("move", e)}
        />
        {handles.map((h) => (
          <span
            key={h.kind}
            className={`edit-transform-handle ${h.className}`}
            onPointerDown={(e) => startDrag(h.kind, e)}
          />
        ))}
      </div>
    </div>
  );
}
