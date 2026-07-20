/**
 * 资产关联谱系面板：展示 incoming/outgoing 关联边，支持点击跳转。
 */

import { useCallback, useEffect, useState } from "react";
import type { AssetLineageView, LineageEdge } from "../types/lineage";
import { KIND_LABEL, RELATION_LABEL } from "../types/lineage";

const API = "/api";

interface AssetLineagePanelProps {
  projectId: string;
  assetId: string;
  onNavigateAsset?: (id: string, kind: string) => void;
}

/** 拉取并展示单资产谱系关联列表。 */
export function AssetLineagePanel({
  projectId,
  assetId,
  onNavigateAsset,
}: AssetLineagePanelProps) {
  const [view, setView] = useState<AssetLineageView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/projects/${projectId}/assets/${assetId}/lineage`);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(String(body.detail ?? `加载关联失败 (${r.status})`));
      }
      setView((await r.json()) as AssetLineageView);
    } catch (err) {
      setError((err as Error).message);
      setView(null);
    } finally {
      setLoading(false);
    }
  }, [projectId, assetId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="muted">加载关联资产…</p>;
  }
  if (error) {
    return <p className="board-error">{error}</p>;
  }
  if (!view) {
    return null;
  }

  const incoming = view.incoming ?? [];
  const outgoing = view.outgoing ?? [];

  if (incoming.length === 0 && outgoing.length === 0) {
    return <p className="muted">暂无关联资产记录</p>;
  }

  return (
    <div className="asset-lineage-panel">
      {incoming.length > 0 && (
        <LineageSection
          title="上游 / 引用自"
          edges={incoming}
          pick="source"
          onNavigate={onNavigateAsset}
        />
      )}
      {outgoing.length > 0 && (
        <LineageSection
          title="下游 / 被用于"
          edges={outgoing}
          pick="target"
          onNavigate={onNavigateAsset}
        />
      )}
    </div>
  );
}

function LineageSection({
  title,
  edges,
  pick,
  onNavigate,
}: {
  title: string;
  edges: LineageEdge[];
  pick: "source" | "target";
  onNavigate?: (id: string, kind: string) => void;
}) {
  return (
    <div className="lineage-section">
      <h5 className="lineage-section-title">{title}</h5>
      <ul className="lineage-edge-list">
        {edges.map((edge) => {
          const node = edge[pick];
          const relationLabel = RELATION_LABEL[edge.relation] ?? edge.relation;
          const kindLabel = KIND_LABEL[node.kind] ?? node.kind;
          const ctx = edge.context ?? {};
          const extra =
            ctx.shot_order !== undefined
              ? `镜 ${Number(ctx.shot_order) + 1}`
              : ctx.ref_key
                ? String(ctx.ref_key)
                : "";
          return (
            <li key={edge.id} className="lineage-edge-item">
              <span className="meta-chip lineage-relation">{relationLabel}</span>
              <span className="meta-chip">{kindLabel}</span>
              {onNavigate ? (
                <button
                  type="button"
                  className="lineage-link-btn"
                  onClick={() => onNavigate(node.id, node.kind)}
                >
                  {node.name}
                </button>
              ) : (
                <span>{node.name}</span>
              )}
              {extra && <span className="muted"> · {extra}</span>}
              <code className="lineage-id">{node.id}</code>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
