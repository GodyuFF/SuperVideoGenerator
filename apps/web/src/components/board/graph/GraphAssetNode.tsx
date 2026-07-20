/**
 * 关系图自定义节点：左侧 kind 色条、标题与副标题截断。
 */

import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

/** 关系图节点 data 载荷。 */
export type GraphAssetNodeData = {
  label: string;
  subtitle?: string;
  kind: string;
};

/** 关系图资产节点组件。 */
function GraphAssetNodeComponent({ data, selected }: NodeProps<Node<GraphAssetNodeData>>) {
  return (
    <div
      className={`graph-asset-node${selected ? " is-selected" : ""}`}
      data-kind={data.kind}
      title={data.subtitle ? `${data.label}\n${data.subtitle}` : data.label}
    >
      <Handle type="target" position={Position.Left} className="graph-asset-handle" />
      <div className="graph-asset-node-bar" aria-hidden />
      <div className="graph-asset-node-body">
        <span className="graph-asset-node-label">{data.label}</span>
        {data.subtitle ? (
          <span className="graph-asset-node-subtitle">{data.subtitle}</span>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} className="graph-asset-handle" />
    </div>
  );
}

export const GraphAssetNode = memo(GraphAssetNodeComponent);
