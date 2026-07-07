/**
 * 项目首页：列出全部项目，支持新建与批量删除。
 */

import { useCallback, useEffect, useState } from "react";
import {
  createProject,
  deleteProjectsBatchApi,
  fetchProjectList,
  type ProjectListItem,
} from "../hooks/useApi";

interface ProjectHomePageProps {
  onOpenProject: (projectId: string) => void;
  onOpenSettings: () => void;
  onOpenAgents: () => void;
  onOpenLogs: () => void;
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
}: ProjectHomePageProps) {
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
    <div className="project-home">
      <header className="top-bar">
        <h1>SuperVideoGenerator</h1>
        <span className="status-badge muted-badge">项目列表</span>
        <div className="top-bar-spacer" />
        <button type="button" className="btn-secondary btn-config" onClick={onOpenAgents}>
          Agent 配置
        </button>
        <button type="button" className="btn-secondary btn-config" onClick={onOpenLogs}>
          查看日志
        </button>
        <button type="button" className="btn-secondary btn-config" onClick={onOpenSettings}>
          AI 配置
        </button>
      </header>

      <main className="project-home-main">
        <div className="project-home-toolbar">
          <h2>我的项目</h2>
          <div className="project-home-actions">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={loading || projects.length === 0}
              onClick={toggleSelectAll}
            >
              {selected.size === projects.length && projects.length > 0
                ? "取消全选"
                : "全选"}
            </button>
            <button
              type="button"
              className="btn-danger btn-sm"
              disabled={deleting || selected.size === 0}
              onClick={() => void handleBatchDelete()}
            >
              {deleting ? "删除中…" : `删除选中 (${selected.size})`}
            </button>
            <button
              type="button"
              className="btn-primary btn-sm"
              disabled={creating}
              onClick={() => void handleCreate()}
            >
              {creating ? "创建中…" : "＋ 新建项目"}
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
              ＋ 新建项目
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
                  <p className="muted project-home-meta">
                    创建于 {formatDate(project.created_at)}
                  </p>
                  <span className="project-home-open">进入项目 →</span>
                </button>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
