/**
 * 关系图看板：基于 nodes/edges 的简易 SVG 布局
 */

import type { BoardEdge, BoardNode } from "../../types/board";

const KIND_COLOR: Record<string, string> = {
  project: "#1d4ed8",
  script: "#1d9bf0",
  character: "#22c55e",
  scene: "#84cc16",
  prop: "#a3e635",
  plot: "#14b8a6",
  video_plan: "#06b6d4",
  image: "#f97316",
  video: "#ef4444",
  audio: "#a855f7",
  final: "#dc2626",
};

interface GraphBoardProps {
  nodes: BoardNode[];
  edges: BoardEdge[];
}

export function GraphBoard({ nodes, edges }: GraphBoardProps) {
  if (nodes.length === 0) {
    return <p className="muted board-empty">暂无关联数据，生成剧本后将自动构图。</p>;
  }

  const byGroup: Record<string, BoardNode[]> = {};
  for (const n of nodes) {
    const g = n.group ?? "default";
    byGroup[g] = byGroup[g] ?? [];
    byGroup[g].push(n);
  }

  const groupOrder = ["project", "scripts", "shared_pool"];
  const orderedGroups = [
    ...groupOrder.filter((g) => byGroup[g]),
    ...Object.keys(byGroup).filter((g) => !groupOrder.includes(g) && !g.startsWith("script_")),
    ...Object.keys(byGroup).filter((g) => g.startsWith("script_")),
  ];

  const positions = new Map<string, { x: number; y: number }>();
  let row = 0;
  const colWidth = 160;
  const rowHeight = 72;

  for (const group of orderedGroups) {
    const items = byGroup[group] ?? [];
    items.forEach((node, col) => {
      positions.set(node.id, { x: 40 + col * colWidth, y: 40 + row * rowHeight });
    });
    row += 1;
  }

  const maxX = Math.max(...[...positions.values()].map((p) => p.x), 200) + 120;
  const maxY = Math.max(...[...positions.values()].map((p) => p.y), 100) + 60;

  return (
    <div className="graph-board-wrap">
      <svg
        className="graph-board-svg"
        viewBox={`0 0 ${maxX} ${maxY}`}
        role="img"
        aria-label="资产关联图"
      >
        {edges.map((e) => {
          const from = positions.get(e.source);
          const to = positions.get(e.target);
          if (!from || !to) return null;
          const mx = (from.x + to.x) / 2;
          const my = (from.y + to.y) / 2;
          return (
            <g key={e.id}>
              <line
                x1={from.x + 60}
                y1={from.y + 24}
                x2={to.x + 60}
                y2={to.y + 24}
                stroke="#536471"
                strokeWidth={1.5}
                markerEnd="url(#arrow)"
              />
              {e.label && (
                <text x={mx + 60} y={my + 18} fill="#71767b" fontSize={10} textAnchor="middle">
                  {e.label}
                </text>
              )}
            </g>
          );
        })}
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#536471" />
          </marker>
        </defs>
        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const fill = KIND_COLOR[n.kind] ?? "#38444d";
          return (
            <g key={n.id} transform={`translate(${p.x}, ${p.y})`}>
              <rect
                width={120}
                height={48}
                rx={6}
                fill={fill}
                fillOpacity={0.2}
                stroke={fill}
                strokeWidth={1.5}
              />
              <text x={8} y={18} fill="#e7e9ea" fontSize={11} fontWeight={600}>
                {n.label.length > 14 ? `${n.label.slice(0, 14)}…` : n.label}
              </text>
              {n.subtitle && (
                <text x={8} y={34} fill="#71767b" fontSize={9}>
                  {n.subtitle.length > 16 ? `${n.subtitle.slice(0, 16)}…` : n.subtitle}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="graph-legend">
        {Object.entries(KIND_COLOR).slice(0, 6).map(([k, c]) => (
          <span key={k} className="legend-item">
            <span className="legend-dot" style={{ background: c }} />
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}
