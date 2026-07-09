/**
 * 加载 SVF 剪辑能力枚举（运镜/转场/背景/导出限制）。
 */

import type { EditCapabilities } from "../../edit/types";

const API = "/api";

/** 获取 edit capabilities，失败时返回空对象。 */
export async function fetchEditCapabilities(): Promise<EditCapabilities | null> {
  try {
    const res = await fetch(`${API}/edit/capabilities`);
    if (!res.ok) return null;
    return (await res.json()) as EditCapabilities;
  } catch {
    return null;
  }
}
