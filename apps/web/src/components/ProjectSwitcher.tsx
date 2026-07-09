/**
 * 项目切换：本地最近项目 + 新建/加载
 */

import { useCallback, useEffect, useState } from "react";
import { useAppTranslation } from "../i18n/useAppTranslation";
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
  const { t } = useAppTranslation(["nav", "common"]);
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
        {current?.title ?? t("nav:currentProject")} ▾
      </button>
      {open && (
        <div className="project-switcher-menu">
          <div className="project-menu-actions">
            <button type="button" onClick={handleCreate}>
              {t("nav:newProject")}
            </button>
            <button type="button" onClick={refresh} disabled={loading}>
              {loading ? t("common:actions.refreshing") : t("nav:loadFromStorage")}
            </button>
          </div>

          {recent.length > 0 && (
            <>
              <p className="menu-section-title">{t("nav:recentScripts")}</p>
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

          <p className="menu-section-title">{t("nav:serverProjects")}</p>
          <ul>
            {remoteProjects.length === 0 && (
              <li className="muted menu-empty">{t("nav:noProjects")}</li>
            )}
            {remoteProjects.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={p.id === projectId && !scriptId ? "active" : ""}
                  onClick={() => pickProject(p.id, p.title)}
                >
                  {p.title}
                  <span className="muted"> · {t("nav:scriptCount", { count: p.script_count })}</span>
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
