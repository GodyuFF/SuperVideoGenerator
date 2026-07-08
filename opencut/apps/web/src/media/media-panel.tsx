/** 媒体资产面板 */

import { useEditorStore } from "../editor/editor-store";
import type { MediaAsset } from "../editor/types";

export function MediaPanel() {
  const mediaAssets = useEditorStore((s) => s.mediaAssets);

  if (mediaAssets.length === 0) {
    return (
      <div className="media-panel">
        <h3 className="media-panel-title">素材库</h3>
        <p className="media-panel-empty muted">暂无可用素材</p>
      </div>
    );
  }

  function handleDragStart(e: React.DragEvent, item: MediaAsset) {
    e.dataTransfer.setData("text/media-id", item.id);
    e.dataTransfer.effectAllowed = "copy";
  }

  return (
    <div className="media-panel">
      <h3 className="media-panel-title">素材库 ({mediaAssets.length})</h3>
      <div className="media-panel-list">
        {mediaAssets.map((item) => (
          <div
            key={item.id}
            className="media-item"
            draggable
            onDragStart={(e) => handleDragStart(e, item)}
            title={`${item.name} · ${item.type}`}
          >
            <span className="media-item-type">
              {item.type === "image"
                ? "🖼"
                : item.type === "audio"
                  ? "🎵"
                  : item.type === "video"
                    ? "🎬"
                    : "📁"}
            </span>
            <span className="media-item-name">{item.name}</span>
            <span className="media-item-duration">
              {item.durationMs ? formatDuration(item.durationMs) : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
