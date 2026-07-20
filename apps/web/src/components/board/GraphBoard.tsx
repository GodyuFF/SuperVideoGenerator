/**
 * 关系图看板：React Flow + dagre LR 布局，支持缩放平移与节点预览侧栏。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { BoardEdge, BoardNode } from "../../types/board";
import { GraphAssetNode, type GraphAssetNodeData } from "./graph/GraphAssetNode";
import { GraphNodeInspector } from "./graph/GraphNodeInspector";
import { LEGEND_KINDS } from "./graph/kindColors";
import { useGraphThemeColors } from "./graph/useGraphThemeColors";
import { layoutProjectGraph } from "./graph/layoutProjectGraph";
import "./graph/graph-board.css";

const nodeTypes = { asset: GraphAssetNode };

interface GraphBoardProps {
  nodes: BoardNode[];
  edges: BoardEdge[];
  /** 从预览侧栏打开完整资产详情。 */
  onOpenDetail?: (node: BoardNode) => void;
}

/** 将 API 节点转为 React Flow 节点。 */
function toFlowNodes(boardNodes: BoardNode[]): Node<GraphAssetNodeData>[] {
  return boardNodes.map((n) => ({
    id: n.id,
    type: "asset",
    position: { x: 0, y: 0 },
    data: {
      label: n.label,
      subtitle: n.subtitle,
      kind: n.kind,
    },
  }));
}

/** 将 API 边转为 React Flow 边（smoothstep）。 */
function toFlowEdges(boardEdges: BoardEdge[]): Edge[] {
  return boardEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    label: e.label,
    pathOptions: { borderRadius: 16 },
    animated: e.relation === "rag_reuse",
  }));
}

/** 画布挂载后自动 fitView。 */
function GraphFitView({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fitView({ padding: 0.18, duration: 280 });
    }, 50);
    return () => window.clearTimeout(timer);
  }, [fitView, nodeCount]);

  return null;
}

/** 关系图主画布（需在 ReactFlowProvider 内）。 */
function GraphBoardCanvas({
  boardNodes,
  boardEdges,
  onOpenDetail,
}: {
  boardNodes: BoardNode[];
  boardEdges: BoardEdge[];
  onOpenDetail?: (node: BoardNode) => void;
}) {
  const { t } = useAppTranslation(["board"]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const graphTheme = useGraphThemeColors();

  const { nodes: flowNodes, edges: flowEdges } = useMemo(() => {
    const rawNodes = toFlowNodes(boardNodes);
    const rawEdges = toFlowEdges(boardEdges);
    return layoutProjectGraph(rawNodes, rawEdges);
  }, [boardNodes, boardEdges]);

  const displayNodes = useMemo(
    () => flowNodes.map((n) => ({ ...n, selected: n.id === selectedId })),
    [flowNodes, selectedId],
  );

  const selectedNode = useMemo(
    () => (selectedId ? boardNodes.find((n) => n.id === selectedId) ?? null : null),
    [boardNodes, selectedId],
  );

  const handleNodeClick: NodeMouseHandler = useCallback((_event, node) => {
    setSelectedId(node.id);
  }, []);

  const handlePaneClick = useCallback(() => {
    setSelectedId(null);
  }, []);

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedId(nodeId);
  }, []);

  const miniMapNodeColor = useCallback(
    (node: Node<GraphAssetNodeData>) => graphTheme.getKindColor(node.data?.kind ?? ""),
    [graphTheme],
  );

  return (
    <div className="graph-board-root">
      <div className="graph-board-canvas">
        <ReactFlow
          nodes={displayNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
          fitView
          minZoom={0.15}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          panOnScroll
          zoomOnScroll
          zoomOnPinch
          aria-label={t("board:graph.canvasLabel")}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color={graphTheme.dotColor}
          />
          <Controls
            showInteractive={false}
            position="bottom-left"
            aria-label={t("board:graph.controlsLabel")}
          />
          <MiniMap
            nodeColor={miniMapNodeColor}
            maskColor={graphTheme.minimapMaskColor}
            position="bottom-right"
            aria-label={t("board:graph.minimapLabel")}
          />
          <GraphFitView nodeCount={flowNodes.length} />
        </ReactFlow>
      </div>

      <GraphNodeInspector
        node={selectedNode}
        nodes={boardNodes}
        edges={boardEdges}
        onClose={() => setSelectedId(null)}
        onOpenDetail={(node) => onOpenDetail?.(node)}
        onSelectNode={handleSelectNode}
      />

      <div className="graph-board-legend" aria-label={t("board:graph.legendLabel")}>
        {LEGEND_KINDS.filter((k) => boardNodes.some((n) => n.kind === k)).map((kind) => (
          <span key={kind} className="legend-item">
            <span className="legend-dot" data-kind={kind} />
            {t(`board:graph.kinds.${kind}`, { defaultValue: kind })}
          </span>
        ))}
      </div>
    </div>
  );
}

/** 项目资产关系图看板入口。 */
export function GraphBoard({ nodes, edges, onOpenDetail }: GraphBoardProps) {
  const { t } = useAppTranslation(["board"]);

  if (nodes.length === 0) {
    return <p className="muted board-empty">{t("board:graph.empty")}</p>;
  }

  return (
    <ReactFlowProvider>
      <GraphBoardCanvas boardNodes={nodes} boardEdges={edges} onOpenDetail={onOpenDetail} />
    </ReactFlowProvider>
  );
}
