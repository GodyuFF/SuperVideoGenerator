import { useMemo, useState } from "react";
import type { MediaBinItem } from "./types";

interface MediaBinProps {
  items: MediaBinItem[];
  onDragStart?: (item: MediaBinItem) => void;
}

type MediaTab = "all" | "image" | "audio" | "video" | "final";

const TAB_LABELS: Record<MediaTab, string> = {
  all: "全部",
  image: "图片",
  audio: "配音",
  video: "视频",
  final: "成片",
};

const TYPE_MAP: Record<string, MediaTab> = {
  image: "image",
  audio: "audio",
  video: "video",
  final: "final",
};

function formatDuration(ms?: number): string {
  if (!ms) return "";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function mediaThumbnail(item: MediaBinItem): string | null {
  if (item.type === "image" || item.type === "video" || item.type === "final") {
    return item.link || item.url || null;
  }
  return null;
}

export function MediaBin({ items, onDragStart }: MediaBinProps) {
  const [tab, setTab] = useState<MediaTab>("all");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    let result = items;
    if (tab !== "all") {
      result = result.filter((item) => TYPE_MAP[item.type] === tab);
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(
        (item) =>
          (item.name || item.id).toLowerCase().includes(q) ||
          item.type.toLowerCase().includes(q)
      );
    }
    return result;
  }, [items, tab, search]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length };
    for (const item of items) {
      const t = TYPE_MAP[item.type] || "all";
      c[t] = (c[t] || 0) + 1;
    }
    return c;
  }, [items]);

  if (items.length === 0) {
    return <p className="muted">暂无可用媒体，请先完成图片/配音生成。</p>;
  }

  return (
    <div className="edit-studio-media-bin">
      <div className="edit-studio-media-search">
        <input
          type="text"
          placeholder="搜索素材…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="edit-studio-media-search-input"
        />
      </div>
      <div className="edit-studio-media-tabs">
        {(Object.keys(TAB_LABELS) as MediaTab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`edit-studio-media-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
            {counts[t] > 0 && <span className="edit-studio-media-count">{counts[t]}</span>}
          </button>
        ))}
      </div>
      <ul className="edit-studio-media-list">
        {filtered.map((item) => {
          const thumb = mediaThumbnail(item);
          return (
            <li
              key={item.id}
              className="edit-studio-media-item"
              draggable={true}
              onDragStart={(e) => {
                e.dataTransfer.setData("text/media-id", item.id);
                onDragStart?.(item);
              }}
              title={`${item.name || item.id} · ${item.type}${item.duration_ms ? ` · ${formatDuration(item.duration_ms)}` : ""}`}
            >
              {thumb ? (
                <img
                  src={thumb}
                  alt={item.name || item.id}
                  className="edit-studio-media-thumb"
                  loading="lazy"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
              ) : (
                <span className="edit-studio-media-type-icon">
                  {item.type === "audio" ? "🎵" : "📁"}
                </span>
              )}
              <span className="edit-studio-media-name">{item.name || item.id}</span>
              <span className="edit-studio-media-type">{item.type}</span>
              {item.duration_ms ? (
                <span className="edit-studio-media-duration">{formatDuration(item.duration_ms)}</span>
              ) : null}
            </li>
          );
        })}
      </ul>
      {filtered.length === 0 && (
        <p className="muted" style={{ padding: "0.5rem", fontSize: "0.75rem" }}>
          无匹配素材
        </p>
      )}
    </div>
  );
}