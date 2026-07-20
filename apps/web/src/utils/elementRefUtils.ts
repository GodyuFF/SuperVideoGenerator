/**
 * element_refs 前端校验：环检测与桶类型常量。
 */

export const ELEMENT_REF_BUCKETS = ["scene", "character", "prop", "frame"] as const;

export type ElementRefBucket = (typeof ELEMENT_REF_BUCKETS)[number];

/** 资产类型 → element_refs 桶（同类型互引）。 */
export const ASSET_TYPE_TO_BUCKET: Record<string, ElementRefBucket> = {
  scene: "scene",
  character: "character",
  prop: "prop",
  frame: "frame",
};

/** 展开 element_refs 全部目标 ID。 */
export function flattenElementRefIds(refs: Record<string, string[]>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const bucket of ELEMENT_REF_BUCKETS) {
    for (const id of refs[bucket] ?? []) {
      if (id && !seen.has(id)) {
        seen.add(id);
        out.push(id);
      }
    }
  }
  return out;
}

/**
 * 检测加入 candidate 后是否形成环。
 * index: assetId → element_refs（全剧本已知部分，至少含候选目标）。
 */
export function wouldCreateElementRefCycle(
  ownerId: string,
  refs: Record<string, string[]>,
  index: Record<string, Record<string, string[]>>,
): boolean {
  const owner = ownerId.trim();
  if (!owner) return false;
  const targets = flattenElementRefIds(refs);
  if (targets.includes(owner)) return true;

  const visit = (current: string, stack: Set<string>): boolean => {
    if (current === owner) return true;
    if (stack.has(current)) return false;
    stack.add(current);
    const nextRefs = index[current];
    if (nextRefs) {
      for (const tid of flattenElementRefIds(nextRefs)) {
        if (visit(tid, stack)) return true;
      }
    }
    return false;
  };

  for (const tid of targets) {
    if (visit(tid, new Set())) return true;
  }
  return false;
}

/** 仅保留指定桶的引用。 */
export function pickElementRefBuckets(
  refs: Record<string, string[]>,
  kinds: ElementRefBucket[],
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const kind of kinds) {
    const ids = (refs[kind] ?? []).filter(Boolean);
    if (ids.length) out[kind] = ids;
  }
  return out;
}
