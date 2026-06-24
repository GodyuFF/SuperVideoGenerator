/** 项目本地记录与看板数据加载 */

const RECENT_KEY = "svg_recent_projects";
const ACTIVE_KEY = "svg_active_session";

export interface LocalProjectRecord {
  projectId: string;
  projectTitle: string;
  scriptId: string;
  scriptTitle: string;
  lastOpened: number;
}

export interface ActiveSession {
  projectId: string;
  scriptId: string;
}

export function loadRecentProjects(): LocalProjectRecord[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as LocalProjectRecord[];
    return Array.isArray(list) ? list.sort((a, b) => b.lastOpened - a.lastOpened) : [];
  } catch {
    return [];
  }
}

export function saveRecentProject(record: Omit<LocalProjectRecord, "lastOpened">) {
  const list = loadRecentProjects().filter((r) => r.projectId !== record.projectId);
  list.unshift({ ...record, lastOpened: Date.now() });
  localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, 20)));
}

export function loadActiveSession(): ActiveSession | null {
  try {
    const raw = localStorage.getItem(ACTIVE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ActiveSession;
    if (parsed.projectId && parsed.scriptId) return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

export function saveActiveSession(session: ActiveSession) {
  localStorage.setItem(ACTIVE_KEY, JSON.stringify(session));
}
