/**
 * 关系图节点预览侧栏：摘要、关联边与打开完整详情入口。
 */

import { useCallback, useEffect } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useAppTranslation } from "../../../i18n/useAppTranslation";
import type { BoardEdge, BoardNode } from "../../../types/board";

interface GraphNodeInspectorProps {
  node: BoardNode | null;
  nodes: BoardNode[];
  edges: BoardEdge[];
  onClose: () => void;
  onOpenDetail: (node: BoardNode) => void;
  onSelectNode: (nodeId: string) => void;
}

/** 按 id 查找节点。 */
function findNode(nodes: BoardNode[], id: string): BoardNode | undefined {
  return nodes.find((n) => n.id === id);
}

/** 关系图右侧预览面板。 */
export function GraphNodeInspector({
  node,
  nodes,
  edges,
  onClose,
  onOpenDetail,
  onSelectNode,
}: GraphNodeInspectorProps) {
  const { t } = useAppTranslation(["board", "common"]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!node) return;
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [node, handleKeyDown]);

  const incoming = node ? edges.filter((e) => e.target === node.id) : [];
  const outgoing = node ? edges.filter((e) => e.source === node.id) : [];

  const copyId = async () => {
    if (!node) return;
    try {
      await navigator.clipboard.writeText(node.id);
    } catch {
      // 剪贴板不可用时静默失败
    }
  };

  const kindLabel =
    t(`board:graph.kinds.${node?.kind ?? "unknown"}`, {
      defaultValue: node?.kind ?? "",
    }) || node?.kind;

  return (
    <AnimatePresence>
      {node ? (
        <motion.aside
          key={node.id}
          className="graph-node-inspector"
          data-kind={node.kind}
          initial={{ x: 24, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 24, opacity: 0 }}
          transition={{ type: "spring", stiffness: 420, damping: 32 }}
          aria-label={t("board:graph.inspectorTitle")}
        >
          <div className="graph-inspector-beam" aria-hidden />
          <header className="graph-inspector-header">
            <span className="graph-inspector-kind">{kindLabel}</span>
            <button
              type="button"
              className="graph-inspector-close"
              onClick={onClose}
              aria-label={t("common:actions.close")}
            >
              ×
            </button>
          </header>
          <h3 className="graph-inspector-title">{node.label}</h3>
          {node.subtitle ? (
            <p className="graph-inspector-subtitle">{node.subtitle}</p>
          ) : null}
          <div className="graph-inspector-id-row">
            <code className="graph-inspector-id">{node.id}</code>
            <button type="button" className="btn-secondary btn-sm" onClick={() => void copyId()}>
              {t("board:graph.copyId")}
            </button>
          </div>

          {incoming.length > 0 ? (
            <section className="graph-inspector-section">
              <h4>{t("board:graph.incoming")}</h4>
              <ul className="graph-inspector-edge-list">
                {incoming.map((edge) => {
                  const peer = findNode(nodes, edge.source);
                  if (!peer) return null;
                  return (
                    <li key={edge.id}>
                      <button
                        type="button"
                        className="graph-inspector-edge-btn"
                        onClick={() => onSelectNode(peer.id)}
                      >
                        <span className="graph-inspector-edge-label">{peer.label}</span>
                        {edge.label ? (
                          <span className="graph-inspector-edge-rel">{edge.label}</span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {outgoing.length > 0 ? (
            <section className="graph-inspector-section">
              <h4>{t("board:graph.outgoing")}</h4>
              <ul className="graph-inspector-edge-list">
                {outgoing.map((edge) => {
                  const peer = findNode(nodes, edge.target);
                  if (!peer) return null;
                  return (
                    <li key={edge.id}>
                      <button
                        type="button"
                        className="graph-inspector-edge-btn"
                        onClick={() => onSelectNode(peer.id)}
                      >
                        <span className="graph-inspector-edge-label">{peer.label}</span>
                        {edge.label ? (
                          <span className="graph-inspector-edge-rel">{edge.label}</span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          <footer className="graph-inspector-footer">
            <button
              type="button"
              className="btn-primary graph-inspector-open"
              onClick={() => onOpenDetail(node)}
            >
              {t("board:graph.openDetail")}
            </button>
          </footer>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
