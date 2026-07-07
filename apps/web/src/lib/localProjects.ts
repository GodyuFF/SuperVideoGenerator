/** 项目本地记录与看板数据加载 */

const RECENT_KEY = "svg_recent_projects";
const ACTIVE_KEY = "svg_active_session";

export type WorkspaceMode = "project" | "script";

export interface LocalProjectRecord {
  projectId: string;
  projectTitle: string;
  scriptId: string;
  scriptTitle: string;
  lastOpened: number;
}

export interface ActiveSession {
  projectId: string;
  scriptId: string | null;
  workspaceMode: WorkspaceMode;
}

function normalizeSession(raw: Record<string, unknown>): ActiveSession | null {
  const projectId = typeof raw.projectId === "string" ? raw.projectId : "";
  if (!projectId) return null;

  // 旧格式：仅有 projectId + scriptId，视为 script 模式
  if (typeof raw.scriptId === "string" && raw.scriptId && raw.workspaceMode === undefined) {
    return { projectId, scriptId: raw.scriptId, workspaceMode: "script" };
  }

  const workspaceMode: WorkspaceMode =
    raw.workspaceMode === "script" ? "script" : "project";
  const scriptId =
    typeof raw.scriptId === "string" && raw.scriptId ? raw.scriptId : null;

  if (workspaceMode === "script" && !scriptId) {
    return { projectId, scriptId: null, workspaceMode: "project" };
  }

  return { projectId, scriptId, workspaceMode };
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

export function removeRecentProjectsByIds(projectIds: string[]) {
  if (projectIds.length === 0) return;
  const drop = new Set(projectIds);
  const list = loadRecentProjects().filter((r) => !drop.has(r.projectId));
  localStorage.setItem(RECENT_KEY, JSON.stringify(list));
}

export function clearActiveSessionIfMatches(projectIds: string[]) {
  const drop = new Set(projectIds);
  const session = loadActiveSession();
  if (session && drop.has(session.projectId)) {
    localStorage.removeItem(ACTIVE_KEY);
  }
}

export function loadActiveSession(): ActiveSession | null {
  try {
    const raw = localStorage.getItem(ACTIVE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return normalizeSession(parsed);
  } catch {
    /* ignore */
  }
  return null;
}

export function saveActiveSession(session: ActiveSession) {
  localStorage.setItem(ACTIVE_KEY, JSON.stringify(session));
}

export function saveWorkspaceSession(
  projectId: string,
  scriptId: string | null,
  workspaceMode: WorkspaceMode
) {
  saveActiveSession({ projectId, scriptId, workspaceMode });
}

const LAST_CONV_PREFIX = "svg_last_conversation:";

/** 读取某剧本上次打开的会话 ID（本地持久化）。 */
export function getLastConversationId(
  projectId: string,
  scriptId: string
): string | null {
  try {
    return localStorage.getItem(`${LAST_CONV_PREFIX}${projectId}:${scriptId}`);
  } catch {
    return null;
  }
}

/** 记录某剧本当前会话 ID，便于再次进入时恢复。 */
export function setLastConversationId(
  projectId: string,
  scriptId: string,
  conversationId: string
) {
  try {
    localStorage.setItem(
      `${LAST_CONV_PREFIX}${projectId}:${scriptId}`,
      conversationId
    );
  } catch {
    /* ignore */
  }
}
