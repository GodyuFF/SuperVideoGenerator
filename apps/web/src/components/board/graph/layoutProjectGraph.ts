/**
 * 使用 dagre 对项目关系图做左→右（LR）分层布局。
 */

import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";
import type { GraphAssetNodeData } from "./GraphAssetNode";

/** 自定义节点宽度（px）。 */
export const GRAPH_NODE_WIDTH = 168;

/** 自定义节点高度（px）。 */
export const GRAPH_NODE_HEIGHT = 56;

/** dagre 布局参数。 */
const LAYOUT_OPTIONS = {
  rankdir: "LR" as const,
  nodesep: 48,
  ranksep: 110,
  marginx: 40,
  marginy: 40,
};

/**
 * 对 React Flow 节点/边应用 LR 布局，同 rank 节点纵向展开以避免单行堆积。
 */
export function layoutProjectGraph(
  nodes: Node<GraphAssetNodeData>[],
  edges: Edge[],
): { nodes: Node<GraphAssetNodeData>[]; edges: Edge[] } {
  if (nodes.length === 0) {
    return { nodes, edges };
  }

  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph(LAYOUT_OPTIONS);

  for (const node of nodes) {
    graph.setNode(node.id, { width: GRAPH_NODE_WIDTH, height: GRAPH_NODE_HEIGHT });
  }

  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);

  const layoutedNodes = nodes.map((node) => {
    const pos = graph.node(node.id);
    return {
      ...node,
      position: {
        x: pos.x - GRAPH_NODE_WIDTH / 2,
        y: pos.y - GRAPH_NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}
