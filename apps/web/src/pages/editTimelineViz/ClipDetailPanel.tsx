/**
 * 选中 clip 的字段详情（只读）。
 */

import type { TrackClip } from "../../edit/types";
import { MediaPreview } from "../../components/MediaPreview";
import { formatMsPrecise } from "./formatMs";

interface ClipDetailPanelProps {
  clip: TrackClip | null;
  onClose: () => void;
}

/** 渲染 JSON 字段块。 */
function JsonBlock({ title, data }: { title: string; data: unknown }) {
  if (data == null || (typeof data === "object" && Object.keys(data as object).length === 0)) {
    return null;
  }
  return (
    <div className="etviz-detail-block">
      <h4>{title}</h4>
      <pre className="etviz-json-snippet">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

/** Clip 详情侧栏。 */
export function ClipDetailPanel({ clip, onClose }: ClipDetailPanelProps) {
  if (!clip) {
    return (
      <aside className="etviz-clip-detail etviz-clip-detail--empty">
        <p className="muted">点击时间轴上的 clip 查看详情</p>
      </aside>
    );
  }

  const start = Number(clip.start_ms ?? 0);
  const end = Number(clip.end_ms ?? 0);
  const track = String(clip.track ?? "—");
  const previewUrl = clip.preview_url ? String(clip.preview_url) : "";

  return (
    <aside className="etviz-clip-detail">
      <div className="etviz-clip-detail-header">
        <h3>{String(clip.label || clip.id || "Clip")}</h3>
        <button type="button" className="btn-secondary btn-sm" onClick={onClose}>
          关闭
        </button>
      </div>
      <dl className="etviz-detail-dl">
        <dt>ID</dt>
        <dd className="mono">{String(clip.id ?? "—")}</dd>
        <dt>轨道</dt>
        <dd>{track}</dd>
        <dt>时间</dt>
        <dd className="tabular-nums">
          {formatMsPrecise(start)} – {formatMsPrecise(end)} ({((end - start) / 1000).toFixed(2)}s)
        </dd>
        {clip.layer_id ? (
          <>
            <dt>图层</dt>
            <dd className="mono">{clip.layer_id}</dd>
          </>
        ) : null}
        {clip.asset_ref ? (
          <>
            <dt>asset_ref</dt>
            <dd className="mono">{clip.asset_ref}</dd>
          </>
        ) : null}
        {clip.motion ? (
          <>
            <dt>运镜</dt>
            <dd>{clip.motion}</dd>
          </>
        ) : null}
      </dl>
      {clip.edit_description ? (
        <div className="etviz-detail-block">
          <h4>剪辑说明</h4>
          <p className="etviz-detail-text">{clip.edit_description}</p>
        </div>
      ) : null}
      {previewUrl ? (
        <div className="etviz-detail-block">
          <h4>预览</h4>
          <MediaPreview
            kind={clip.preview_media_type === "audio" || track === "audio" ? "audio" : "image"}
            url={previewUrl}
            className="etviz-clip-preview"
          />
        </div>
      ) : null}
      <JsonBlock title="transition_in" data={clip.transition_in} />
      <JsonBlock title="transition_out" data={clip.transition_out} />
      <JsonBlock title="background" data={clip.background} />
      <JsonBlock title="motion_detail" data={clip.motion_detail} />
      <JsonBlock title="source_refs" data={clip.source_refs} />
      <JsonBlock title="transform" data={clip.transform} />
      <JsonBlock title="metadata" data={clip.metadata} />
    </aside>
  );
}
