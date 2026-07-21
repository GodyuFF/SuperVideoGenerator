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
  /** 打开指定项目工作台。 */
  onOpenProject: (projectId: string) => void;
  /** 打开 AI 配置页。 */
  onOpenSettings: () => void;
  /** 打开 Agent 配置页。 */
  onOpenAgents: () => void;
  /** 打开交互日志页。 */
  onOpenLogs: () => void;
  /** 可选：打开剪辑时间轴可视化页。 */
  onOpenEditTimelineViz?: () => void;
}

/** 将 ISO 时间格式化为本地可读字符串。 */
function formatDate(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

/**
 * 项目列表首页：Hero + 卡片网格，支持多选批量删除。
 */
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

  /** 从服务端拉取项目列表并裁剪已失效的选中项。 */
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

  /** 切换单个项目的多选勾选状态。 */
  const toggleSelect = (projectId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  };

  /** 全选或清空当前列表选中。 */
  const toggleSelectAll = () => {
    if (selected.size === projects.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(projects.map((p) => p.id)));
    }
  };

  /** 创建新项目并进入工作台。 */
  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const title = t("defaultProjectTitle", {
        ns: "nav",
        date: new Date().toLocaleDateString(),
      });
      const { projectId } = await createProject(title);
      onOpenProject(projectId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  /** 确认后批量删除选中项目。 */
  const handleBatchDelete = async () => {
    if (selected.size === 0) return;
    const ids = [...selected];
    const label =
      ids.length === 1
        ? t("deleteConfirmOne", { ns: "nav" })
        : t("deleteConfirmMany", { ns: "nav", count: ids.length });
    if (!window.confirm(t("deleteConfirm", { ns: "nav", label }))) {
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
      <section className="svf-hero" aria-label={t("heroAria", { ns: "nav" })}>
        <p className="svf-hero-eyebrow">{t("heroEyebrow", { ns: "nav" })}</p>
        <h2 className="svf-hero-title">{t("heroTitle", { ns: "nav" })}</h2>
        <p className="svf-hero-desc">{t("heroDesc", { ns: "nav" })}</p>
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
        <p className="muted loading-inline">{t("loadingProjects", { ns: "nav" })}</p>
      ) : projects.length === 0 ? (
        <div className="project-home-empty">
          <p className="muted">{t("emptyProjectsHint", { ns: "nav" })}</p>
          <button type="button" className="btn-primary" onClick={() => void handleCreate()}>
            {t("newProject", { ns: "nav" })}
          </button>
        </div>
      ) : (
        <div className="project-home-grid">
          {projects.map((project) => {
            const isSelected = selected.has(project.id);
            const scriptCount = project.script_count ?? project.scripts?.length ?? 0;
            return (
              <article
                key={project.id}
                className={`project-home-card${isSelected ? " is-selected" : ""}`}
                aria-selected={isSelected}
              >
                <span className="project-home-card-viewfinder" aria-hidden="true" />
                <label className="project-home-card-check">
                  <input
                    type="checkbox"
                    className="project-home-card-checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(project.id)}
                    onClick={(e) => e.stopPropagation()}
                    aria-label={t("selectProject", {
                      ns: "nav",
                      title: project.title || t("unnamedProject", { ns: "nav" }),
                    })}
                  />
                </label>
                <button
                  type="button"
                  className="project-home-card-body"
                  onClick={() => onOpenProject(project.id)}
                >
                  <strong className="project-home-card-title">
                    {project.title || t("unnamedProject", { ns: "nav" })}
                  </strong>
                  <p className="project-home-card-count muted">
                    {t("scriptCount", { ns: "nav", count: scriptCount })}
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
                    {t("createdAt", { ns: "nav", date: formatDate(project.created_at) })}
                  </p>
                  <span className="project-home-open">{t("enterProject", { ns: "nav" })}</span>
                </button>
              </article>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
