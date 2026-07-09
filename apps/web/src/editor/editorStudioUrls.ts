/** 专业剪辑独立页哈希与打开方式。 */

/** 构建剪辑独立页哈希路由。 */
export function buildEditorStudioHash(projectId: string, scriptId: string): string {
  return `#/project/${encodeURIComponent(projectId)}/script/${encodeURIComponent(scriptId)}/edit`;
}

/** 构建可在系统浏览器中打开的完整 URL。 */
export function buildEditorStudioUrl(projectId: string, scriptId: string): string {
  const base = `${window.location.origin}${window.location.pathname}`;
  return `${base}${buildEditorStudioHash(projectId, scriptId)}`;
}

/** 当前页跳转到剪辑独立页。 */
export function openEditorStudioInSameTab(projectId: string, scriptId: string): void {
  window.location.hash = buildEditorStudioHash(projectId, scriptId);
}

/** 在新浏览器标签页打开剪辑独立页。 */
export function openEditorStudioInNewTab(projectId: string, scriptId: string): void {
  const url = buildEditorStudioUrl(projectId, scriptId);
  const opened = window.open(url, "_blank", "noopener,noreferrer");
  if (!opened) {
    openEditorStudioInSameTab(projectId, scriptId);
  }
}

/** 通知打开此页的工作台刷新剪辑时间轴（新标签保存后）。 */
export function notifyOpenerTimelineReload(scriptId: string): void {
  if (!window.opener || window.opener.closed) return;
  try {
    window.opener.dispatchEvent(
      new CustomEvent("svg:edit-timeline-reloaded", { detail: { scriptId } }),
    );
  } catch {
    // 跨域或 opener 不可访问时忽略
  }
}
