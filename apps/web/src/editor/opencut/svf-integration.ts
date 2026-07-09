/**
 * SVF 集成辅助：供 opencut 内核判断是否为 SVF 托管项目。
 */

/** 判断项目 ID 是否为 SVF 复合键（projectId__scriptId）。 */
export function isSvfProjectKey(key: string): boolean {
  const idx = key.indexOf("__");
  return idx > 0 && idx < key.length - 2;
}

/** 解析 SVF 复合键。 */
export function parseSvfProjectKeyFromId(
  key: string,
): { projectId: string; scriptId: string } | null {
  const idx = key.indexOf("__");
  if (idx <= 0) return null;
  return { projectId: key.slice(0, idx), scriptId: key.slice(idx + 2) };
}

