import type { MediaBinItem } from "./types";

interface MediaBinProps {
  items: MediaBinItem[];
  onDragStart?: (item: MediaBinItem) => void;
}

export function MediaBin({ items, onDragStart }: MediaBinProps) {
  if (items.length === 0) {
    return <p className="muted">暂无可用媒体，请先完成图片/配音生成。</p>;
  }
  return (
    <ul className="edit-studio-media-bin">
      {items.map((item) => (
        <li
          key={item.id}
          className="edit-studio-media-item"
          draggable
          onDragStart={(e) => {
            e.dataTransfer.setData("text/media-id", item.id);
            e.dataTransfer.effectAllowed = "copy";
            onDragStart?.(item);
          }}
        >
          <span className="edit-studio-media-type">{item.type}</span>
          <span className="edit-studio-media-name">{item.name || item.id}</span>
        </li>
      ))}
    </ul>
  );
}
