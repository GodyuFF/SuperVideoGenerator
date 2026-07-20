/**
 * 项目首页：列出全部项目，支持新建与批量删除。
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createProject,
  deleteProjectsBatchApi,
  fetchProjectList,
  type ProjectListItem,
} from "../hooks/useApi";
import { AppShell } from "../components/layout/AppShell";
import { AppNavTrail } from "../components/layout/AppNavTrail";

interface ProjectHomePageProps {
  onOpenProject: (projectId: string) => void;
  onOpenSettings: () => void;
  onOpenAgents: () => void;
  onOpenLogs: () => void;
  onOpenEditTimelineViz?: () => void;
}

function formatDate(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function ProjectHomePage({
  onOpenProject,
  onOpenSettings,
  onOpenAgents,
  onOpenLogs,
  onOpenEditTimelineViz,
}: ProjectHomePageProps) {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const loadProjects = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const list = await fetchProjectList();
      setProjects(list);
      setSelected((prev) => {
        const ids = new Set(list.map((p) => p.id));
        return new Set([...prev].filter((id) => ids.has(id)));
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const toggleSelect = (projectId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === projects.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(projects.map((p) => p.id)));
    }
  };

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const title = `视频项目 ${new Date().toLocaleDateString()}`;
      const { projectId } = await createProject(title);
      onOpenProject(projectId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const handleBatchDelete = async () => {
    if (selected.size === 0) return;
    const ids = [...selected];
    const label = ids.length === 1 ? "该项目" : `选中的 ${ids.length} 个项目`;
    if (!window.confirm(`确定删除${label}？将同时删除磁盘目录与对话数据，且不可恢复。`)) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await deleteProjectsBatchApi(ids);
      await loadProjects();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <AppShell
      pageClass="project-home"
      mainClass="project-home-main"
      badge={<span className="status-badge muted-badge">{t("projectList", { ns: "nav" })}</span>}
      trail={
        <AppNavTrail
          onOpenAgents={onOpenAgents}
          onOpenLogs={onOpenLogs}
          onOpenEditTimelineViz={onOpenEditTimelineViz}
          onOpenSettings={onOpenSettings}
        />
      }
    >
      <section className="svf-hero" aria-label="产品介绍">
        <p className="svf-hero-eyebrow">AI 视频创作工作台</p>
        <h2 className="svf-hero-title">从剧本到成片，一条对话流水线</h2>
        <p className="svf-hero-desc">
          用自然语言驱动多 Agent 协作：写剧本、建分镜、生图配音、剪辑导出。每个项目独立管理，资产可复用。
        </p>
      </section>

      <div className="project-home-toolbar">
          <h2>{t("myProjects", { ns: "nav" })}</h2>
          <div className="project-home-actions">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={loading || projects.length === 0}
              onClick={toggleSelectAll}
            >
              {selected.size === projects.length && projects.length > 0
                ? t("actions.deselectAll", { ns: "common" })
                : t("actions.selectAll", { ns: "common" })}
            </button>
            <button
              type="button"
              className="btn-danger btn-sm"
              disabled={deleting || selected.size === 0}
              onClick={() => void handleBatchDelete()}
            >
              {deleting
                ? t("actions.deleting", { ns: "common" })
                : t("deleteSelected", { ns: "nav", count: selected.size })}
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={creating}
              onClick={() => void handleCreate()}
            >
              {creating ? t("actions.creating", { ns: "common" }) : t("newProject", { ns: "nav" })}
            </button>
          </div>
        </div>

        {error && <p className="error-banner">{error}</p>}

        {loading ? (
          <p className="muted loading-inline">加载项目列表…</p>
        ) : projects.length === 0 ? (
          <div className="project-home-empty">
            <p className="muted">暂无项目，点击「新建项目」开始创作。</p>
            <button type="button" className="btn-primary" onClick={() => void handleCreate()}>
              {t("newProject", { ns: "nav" })}
            </button>
          </div>
        ) : (
          <div className="project-home-grid">
            {projects.map((project) => (
              <article key={project.id} className="project-home-card">
                <label className="project-home-card-check">
                  <input
                    type="checkbox"
                    checked={selected.has(project.id)}
                    onChange={() => toggleSelect(project.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                </label>
                <button
                  type="button"
                  className="project-home-card-body"
                  onClick={() => onOpenProject(project.id)}
                >
                  <strong>{project.title || "未命名项目"}</strong>
                  <p className="muted">
                    {project.script_count ?? project.scripts?.length ?? 0} 个剧本
                  </p>
                  {(project.scripts?.length ?? 0) > 0 && (
                    <ul className="project-home-scripts">
                      {project.scripts!.map((s) => (
                        <li key={s.id}>
                          <span className="board-script-index">
                            {t("scriptIndex", {
                              ns: "board",
                              index: s.script_index ?? "—",
                            })}
                          </span>
                          <span className="project-home-script-title">{s.title}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="muted project-home-meta">
                    创建于 {formatDate(project.created_at)}
                  </p>
                  <span className="project-home-open">{t("enterProject", { ns: "nav" })}</span>
                </button>
              </article>
            ))}
          </div>
        )}
    </AppShell>
  );
}
