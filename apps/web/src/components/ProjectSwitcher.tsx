/**
 * 项目切换：本地最近项目 + 新建/加载
 */

import { useCallback, useEffect, useState } from "react";
import type { ProjectListItem } from "../types/board";
import {
  loadRecentProjects,
  saveRecentProject,
  type LocalProjectRecord,
} from "../lib/localProjects";

const API = "/api";

interface ProjectSwitcherProps {
  projectId: string | null;
  scriptId: string | null;
  onSwitchProject: (projectId: string) => void;
  onEnterScript: (projectId: string, scriptId: string, meta?: { projectTitle?: string; scriptTitle?: string }) => void;
  onCreateNew: () => Promise<void>;
  disabled?: boolean;
}

export function ProjectSwitcher({
  projectId,
  scriptId,
  onSwitchProject,
  onEnterScript,
  onCreateNew,
  disabled,
}: ProjectSwitcherProps) {
  const [open, setOpen] = useState(false);
  const [remoteProjects, setRemoteProjects] = useState<ProjectListItem[]>([]);
  const [recent, setRecent] = useState<LocalProjectRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setRecent(loadRecentProjects());
    try {
      const r = await fetch(`${API}/projects`);
      if (r.ok) setRemoteProjects(await r.json());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  function pickProject(pid: string, title: string) {
    saveRecentProject({
      projectId: pid,
      projectTitle: title,
      scriptId: scriptId ?? "",
      scriptTitle: "",
    });
    onSwitchProject(pid);
    setOpen(false);
  }

  function pickScript(
    pid: string,
    sid: string,
    title: string,
    scriptTitle: string
  ) {
    saveRecentProject({
      projectId: pid,
      projectTitle: title,
      scriptId: sid,
      scriptTitle,
    });
    onEnterScript(pid, sid, { projectTitle: title, scriptTitle });
    setOpen(false);
  }

  async function handleCreate() {
    setOpen(false);
    await onCreateNew();
  }

  const current = remoteProjects.find((p) => p.id === projectId);

  return (
    <div className="project-switcher">
      <button
        type="button"
        className="btn-secondary project-switcher-btn"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        {current?.title ?? "当前项目"} ▾
      </button>
      {open && (
        <div className="project-switcher-menu">
          <div className="project-menu-actions">
            <button type="button" onClick={handleCreate}>
              ＋ 新建项目
            </button>
            <button type="button" onClick={refresh} disabled={loading}>
              {loading ? "刷新中…" : "从本地存储加载列表"}
            </button>
          </div>

          {recent.length > 0 && (
            <>
              <p className="menu-section-title">最近打开的剧本</p>
              <ul>
                {recent.filter((r) => r.scriptId).map((r) => (
                  <li key={`${r.projectId}-${r.scriptId}`}>
                    <button
                      type="button"
                      onClick={() =>
                        pickScript(r.projectId, r.scriptId, r.projectTitle, r.scriptTitle)
                      }
                    >
                      {r.projectTitle} / {r.scriptTitle}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="menu-section-title">服务端项目</p>
          <ul>
            {remoteProjects.length === 0 && (
              <li className="muted menu-empty">暂无项目，请新建</li>
            )}
            {remoteProjects.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={p.id === projectId && !scriptId ? "active" : ""}
                  onClick={() => pickProject(p.id, p.title)}
                >
                  {p.title}
                  <span className="muted"> · {p.script_count} 个剧本</span>
                </button>
                {p.scripts.length > 0 && (
                  <ul className="project-script-sublist">
                    {p.scripts.map((s) => (
                      <li key={s.id}>
                        <button
                          type="button"
                          className={
                            p.id === projectId && s.id === scriptId ? "active" : ""
                          }
                          onClick={() => pickScript(p.id, s.id, p.title, s.title)}
                        >
                          {s.title}
                          <span className="muted"> ({s.status})</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
