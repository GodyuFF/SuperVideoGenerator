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
  onSwitch: (projectId: string, scriptId: string) => void;
  onCreateNew: () => Promise<void>;
  disabled?: boolean;
}

export function ProjectSwitcher({
  projectId,
  scriptId,
  onSwitch,
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

  function pick(projectId: string, scriptId: string, title: string, scriptTitle: string) {
    saveRecentProject({
      projectId,
      projectTitle: title,
      scriptId,
      scriptTitle,
    });
    onSwitch(projectId, scriptId);
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
            <button type="button" onClick={handleCreate}>＋ 新建项目</button>
            <button type="button" onClick={refresh} disabled={loading}>
              {loading ? "刷新中…" : "从本地存储加载列表"}
            </button>
          </div>

          {recent.length > 0 && (
            <>
              <p className="menu-section-title">最近打开（浏览器本地）</p>
              <ul>
                {recent.map((r) => (
                  <li key={`${r.projectId}-${r.scriptId}`}>
                    <button
                      type="button"
                      onClick={() => pick(r.projectId, r.scriptId, r.projectTitle, r.scriptTitle)}
                    >
                      {r.projectTitle} / {r.scriptTitle}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="menu-section-title">服务端项目（data/dev_store.json）</p>
          <ul>
            {remoteProjects.length === 0 && (
              <li className="muted menu-empty">暂无项目，请新建</li>
            )}
            {remoteProjects.map((p) =>
              p.scripts.map((s) => (
                <li key={`${p.id}-${s.id}`}>
                  <button
                    type="button"
                    className={p.id === projectId && s.id === scriptId ? "active" : ""}
                    onClick={() => pick(p.id, s.id, p.title, s.title)}
                  >
                    {p.title} · {s.title}
                    <span className="muted"> ({s.status})</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
