/** Agent 工作台工具分组：跨范围读取与单范围归类。 */

import type { AgentToolOption } from "../types/agentConfig";

/** 跨范围读取分组在 UI 中的固定 key。 */
export const MULTI_SCOPE_READ_GROUP = "__multi_scope_read__";

/** 作用范围在 UI 中的展示顺序（生产语义）。 */
export const TOOL_SCOPE_ORDER = [
  "project",
  "orchestration",
  "script",
  "plot",
  "character",
  "scene",
  "prop",
  "frame",
  "image",
  "storyboard",
  "shot",
  "plan",
  "video",
  "audio",
  "timeline",
  "clip",
  "asset",
  "web",
  "export",
] as const;

/** 操作意义在 UI 中的展示顺序。 */
export const TOOL_OPERATION_ORDER = [
  "read",
  "create",
  "update",
  "delete",
  "generate",
  "scan",
  "search",
  "sync",
  "persist",
  "analyze",
  "validate",
  "compose",
  "export",
  "delegate",
  "control",
] as const;

/** 单组内的工具条目。 */
export interface AgentToolOperationGroup {
  operation: string;
  tools: AgentToolOption[];
}

/** 按作用范围与操作意义嵌套分组后的结构。 */
export interface AgentToolScopeGroup {
  scope: string;
  operations: AgentToolOperationGroup[];
}

/** 工作台工具目录布局：跨范围读取置顶，其余按范围分组。 */
export interface AgentToolCatalogLayout {
  multiScopeRead: AgentToolOption[];
  byScope: AgentToolScopeGroup[];
}

/** 是否为跨多类持久化实体的只读查询工具。 */
export function isMultiScopeReadTool(tool: AgentToolOption): boolean {
  if (tool.multi_scope_read === true) return true;
  if (tool.multi_scope_read === false) return false;
  const ops = tool.operations ?? [];
  const readPrimary =
    tool.read_only || ops.length === 0 || ["read", "scan", "validate", "analyze"].includes(ops[0]);
  if (!readPrimary) return false;
  const reads = (tool.affected_data_read ?? []).filter((e) => !e.includes("无"));
  return reads.length >= 2;
}

/** 取工具的主作用范围（scopes 首项，否则 project）。 */
export function primaryToolScope(tool: Pick<AgentToolOption, "scopes">): string {
  const scopes = tool.scopes ?? [];
  return scopes[0] ?? "project";
}

/** 取工具的主操作意义（operations 首项，否则 read）。 */
export function primaryToolOperation(tool: Pick<AgentToolOption, "operations" | "read_only">): string {
  const operations = tool.operations ?? [];
  if (operations.length > 0) return operations[0];
  return tool.read_only ? "read" : "create";
}

function scopeSortIndex(scope: string): number {
  const idx = TOOL_SCOPE_ORDER.indexOf(scope as (typeof TOOL_SCOPE_ORDER)[number]);
  return idx >= 0 ? idx : TOOL_SCOPE_ORDER.length + 1;
}

function operationSortIndex(operation: string): number {
  const idx = TOOL_OPERATION_ORDER.indexOf(operation as (typeof TOOL_OPERATION_ORDER)[number]);
  return idx >= 0 ? idx : TOOL_OPERATION_ORDER.length + 1;
}

/** 将工具列表按作用范围 → 操作意义两级分组并排序。 */
export function groupToolsByScopeAndOperation(tools: AgentToolOption[]): AgentToolScopeGroup[] {
  const byScope = new Map<string, Map<string, AgentToolOption[]>>();

  for (const tool of tools) {
    const scope = primaryToolScope(tool);
    const operation = primaryToolOperation(tool);
    const scopeMap = byScope.get(scope) ?? new Map<string, AgentToolOption[]>();
    const list = scopeMap.get(operation) ?? [];
    list.push(tool);
    scopeMap.set(operation, list);
    byScope.set(scope, scopeMap);
  }

  const scopes = [...byScope.keys()].sort((a, b) => scopeSortIndex(a) - scopeSortIndex(b));

  return scopes.map((scope) => {
    const operationMap = byScope.get(scope)!;
    const operationKeys = [...operationMap.keys()].sort(
      (a, b) => operationSortIndex(a) - operationSortIndex(b),
    );
    return {
      scope,
      operations: operationKeys.map((operation) => ({
        operation,
        tools: operationMap.get(operation)!.sort((a, b) => a.action.localeCompare(b.action)),
      })),
    };
  });
}

/** 拆分跨范围读取工具并分组其余工具。 */
export function layoutAgentToolCatalog(tools: AgentToolOption[]): AgentToolCatalogLayout {
  const multiScopeRead: AgentToolOption[] = [];
  const rest: AgentToolOption[] = [];
  for (const tool of tools) {
    if (isMultiScopeReadTool(tool)) {
      multiScopeRead.push(tool);
    } else {
      rest.push(tool);
    }
  }
  multiScopeRead.sort((a, b) => a.action.localeCompare(b.action));
  return {
    multiScopeRead,
    byScope: groupToolsByScopeAndOperation(rest),
  };
}
