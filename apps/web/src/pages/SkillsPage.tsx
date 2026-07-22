/**
 * Skill 库管理页：列表、格式校验导入、删除用户包。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AppShell } from "../components/layout/AppShell";
import { LocaleSwitcher } from "../i18n/LocaleSwitcher";
import { ThemeToggle } from "../components/theme/ThemeToggle";
import type { SkillMetaItem } from "../types/agentConfig";
import "../styles/skills-library.css";

const API = "/api";

interface SkillsPageProps {
  /** 返回上一页。 */
  onBack: () => void;
  /** 跳转 Agent 配置（关联 Skill）。 */
  onOpenAgents?: () => void;
}

interface SkillCheckItem {
  id: string;
  label: string;
  ok: boolean;
  required?: boolean;
  detail?: string;
}

interface SkillValidationReport {
  ok: boolean;
  skill_id?: string | null;
  title?: string | null;
  description?: string;
  aliases?: string[];
  already_exists?: boolean;
  checks?: SkillCheckItem[];
  errors?: string[];
  warnings?: string[];
}

/** 解析 FastAPI detail（字符串或带 validation 的对象）。 */
function parseApiDetail(detail: unknown): { message: string; validation?: SkillValidationReport } {
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; validation?: SkillValidationReport; detail?: unknown };
    if (d.validation) {
      return {
        message: d.message || d.validation.errors?.[0] || "校验失败",
        validation: d.validation,
      };
    }
    if (typeof d.message === "string") return { message: d.message };
  }
  if (Array.isArray(detail)) {
    return {
      message: detail
        .map((x) =>
          typeof x === "object" && x && "msg" in x
            ? String((x as { msg: unknown }).msg)
            : String(x),
        )
        .join("; "),
    };
  }
  return { message: "请求失败" };
}

/** Skill 库：胶片匣式目录 + 装载闸校验导入。 */
export function SkillsPage({ onBack, onOpenAgents }: SkillsPageProps) {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<SkillMetaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [validation, setValidation] = useState<SkillValidationReport | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  /** 拉取全部 Skill。 */
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/skills`);
      if (!r.ok) throw new Error(await r.text());
      const list = (await r.json()) as SkillMetaItem[];
      setSkills(Array.isArray(list) ? list : []);
    } catch (err) {
      setError((err as Error).message || t("skills.loadFailed", { ns: "settings" }));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /** 对 zip 做格式校验（不落盘）。 */
  const runValidate = useCallback(
    async (file: File) => {
      setStatusMsg(null);
      setError(null);
      setPendingFile(file);
      setOverwrite(false);
      const body = new FormData();
      body.append("file", file);
      const r = await fetch(`${API}/skills/validate`, { method: "POST", body });
      const data = (await r.json().catch(() => ({}))) as SkillValidationReport & {
        detail?: unknown;
      };
      if (!r.ok) {
        const parsed = parseApiDetail(data.detail ?? data);
        setValidation(parsed.validation ?? null);
        setError(parsed.message);
        return;
      }
      setValidation(data);
      if (data.already_exists) {
        setOverwrite(false);
      }
    },
    [],
  );

  /** 确认导入当前待处理文件。 */
  const confirmImport = useCallback(async () => {
    if (!pendingFile) return;
    if (validation && !validation.ok) return;
    setImporting(true);
    setError(null);
    setStatusMsg(null);
    try {
      const body = new FormData();
      body.append("file", pendingFile);
      body.append("overwrite", overwrite ? "true" : "false");
      const r = await fetch(`${API}/skills/import`, { method: "POST", body });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        const parsed = parseApiDetail(data.detail ?? data);
        if (parsed.validation) setValidation(parsed.validation);
        if (r.status === 409) {
          setOverwrite(false);
          setError(parsed.message);
          return;
        }
        throw new Error(parsed.message);
      }
      if (data.validation) setValidation(data.validation as SkillValidationReport);
      setStatusMsg(
        t("skills.imported", { ns: "settings", id: data.id || validation?.skill_id }),
      );
      setPendingFile(null);
      await refresh();
    } catch (err) {
      setError((err as Error).message || t("skills.importFailed", { ns: "settings" }));
    } finally {
      setImporting(false);
    }
  }, [pendingFile, validation, overwrite, refresh, t]);

  /** 删除用户 Skill。 */
  const handleDelete = useCallback(
    async (skillId: string) => {
      if (
        !window.confirm(
          t("skills.deleteConfirm", { ns: "settings", id: skillId }),
        )
      ) {
        return;
      }
      setError(null);
      try {
        const r = await fetch(`${API}/skills/${encodeURIComponent(skillId)}`, {
          method: "DELETE",
        });
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(parseApiDetail(data.detail ?? data).message);
        }
        setStatusMsg(t("skills.deleted", { ns: "settings", id: skillId }));
        await refresh();
      } catch (err) {
        setError((err as Error).message || t("skills.deleteFailed", { ns: "settings" }));
      }
    },
    [refresh, t],
  );

  /** 处理拖放 / 选文件。 */
  const acceptFile = useCallback(
    (file: File | null) => {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".zip")) {
        setError(t("skills.zipOnly", { ns: "settings" }));
        return;
      }
      void runValidate(file);
    },
    [runValidate, t],
  );

  const userCount = skills.filter((s) => s.source === "user" || s.deletable).length;
  const builtinCount = skills.length - userCount;

  return (
    <AppShell
      pageClass="settings-page skills-library-page"
      mainClass="settings-main skills-library-main"
      className="settings-top-bar"
      title={t("skillLibrary", { ns: "nav" })}
      lead={
        <button type="button" className="btn-secondary" onClick={onBack}>
          {t("backHome", { ns: "nav" })}
        </button>
      }
      trail={
        <>
          <ThemeToggle />
          <LocaleSwitcher />
          {onOpenAgents && (
            <button type="button" className="btn-secondary btn-config" onClick={onOpenAgents}>
              {t("agentConfig", { ns: "nav" })}
            </button>
          )}
        </>
      }
    >
      <header className="sk-hero">
        <p className="sk-hero-eyebrow">{t("skills.eyebrow", { ns: "settings" })}</p>
        <h1 className="sk-hero-title">{t("skills.title", { ns: "settings" })}</h1>
        <p className="sk-hero-desc">{t("skills.desc", { ns: "settings" })}</p>
        <div className="sk-stats" aria-label={t("skills.statsAria", { ns: "settings" })}>
          <div className="sk-stat">
            <span className="sk-stat-value">{skills.length}</span>
            <span className="sk-stat-label">{t("skills.statTotal", { ns: "settings" })}</span>
          </div>
          <div className="sk-stat">
            <span className="sk-stat-value">{builtinCount}</span>
            <span className="sk-stat-label">{t("skills.statBuiltin", { ns: "settings" })}</span>
          </div>
          <div className="sk-stat">
            <span className="sk-stat-value">{userCount}</span>
            <span className="sk-stat-label">{t("skills.statUser", { ns: "settings" })}</span>
          </div>
        </div>
      </header>

      <section className="sk-gate" aria-labelledby="sk-gate-title">
        <div className="sk-gate-head">
          <h2 id="sk-gate-title" className="sk-section-title">
            {t("skills.gateTitle", { ns: "settings" })}
          </h2>
          <p className="sk-section-desc">{t("skills.gateDesc", { ns: "settings" })}</p>
        </div>
        <div
          className={`sk-dropzone${dragOver ? " is-dragover" : ""}${validation ? " has-report" : ""}`}
          onDragEnter={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            acceptFile(e.dataTransfer.files?.[0] ?? null);
          }}
        >
          <div className="sk-dropzone-rail" aria-hidden />
          <div className="sk-dropzone-body">
            <p className="sk-dropzone-lead">{t("skills.dropLead", { ns: "settings" })}</p>
            <p className="sk-dropzone-hint">{t("skills.dropHint", { ns: "settings" })}</p>
            <button
              type="button"
              className="sk-browse-btn"
              disabled={importing}
              onClick={() => inputRef.current?.click()}
            >
              {t("skills.browseZip", { ns: "settings" })}
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".zip,application/zip"
              hidden
              onChange={(e) => {
                acceptFile(e.target.files?.[0] ?? null);
                e.target.value = "";
              }}
            />
            {pendingFile && (
              <p className="sk-pending-file">
                <span className="sk-mono">{pendingFile.name}</span>
                <span className="sk-muted">
                  {" "}
                  · {(pendingFile.size / 1024).toFixed(1)} KB
                </span>
              </p>
            )}
          </div>
        </div>

        {validation && (
          <div
            className={`sk-report${validation.ok ? " is-ok" : " is-bad"}`}
            role="status"
          >
            <header className="sk-report-head">
              <span className="sk-report-eyebrow">
                {validation.ok
                  ? t("skills.reportOk", { ns: "settings" })
                  : t("skills.reportBad", { ns: "settings" })}
              </span>
              {validation.skill_id && (
                <span className="sk-report-id">/{validation.skill_id}</span>
              )}
              {validation.title && (
                <span className="sk-report-title">{validation.title}</span>
              )}
            </header>
            <ul className="sk-check-list">
              {(validation.checks ?? []).map((c) => (
                <li
                  key={c.id}
                  className={`sk-check${c.ok ? " is-pass" : c.required === false ? " is-warn" : " is-fail"}`}
                >
                  <span className="sk-check-mark" aria-hidden>
                    {c.ok ? "✓" : c.required === false ? "·" : "✗"}
                  </span>
                  <span className="sk-check-label">{c.label}</span>
                  {c.detail ? <span className="sk-check-detail">{c.detail}</span> : null}
                </li>
              ))}
            </ul>
            {(validation.warnings ?? []).length > 0 && (
              <ul className="sk-warn-list">
                {validation.warnings!.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
            {validation.already_exists && validation.ok && (
              <label className="sk-overwrite">
                <input
                  type="checkbox"
                  checked={overwrite}
                  onChange={(e) => setOverwrite(e.target.checked)}
                />
                {t("skills.overwriteConfirm", {
                  ns: "settings",
                  id: validation.skill_id,
                })}
              </label>
            )}
            <div className="sk-report-actions">
              <button
                type="button"
                className="sk-import-btn"
                disabled={
                  importing ||
                  !validation.ok ||
                  !pendingFile ||
                  (Boolean(validation.already_exists) && !overwrite)
                }
                onClick={() => void confirmImport()}
              >
                {importing
                  ? t("skills.importing", { ns: "settings" })
                  : t("skills.confirmImport", { ns: "settings" })}
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={importing}
                onClick={() => {
                  setPendingFile(null);
                  setValidation(null);
                  setOverwrite(false);
                }}
              >
                {t("actions.cancel", { ns: "common" })}
              </button>
            </div>
          </div>
        )}
      </section>

      {statusMsg && <div className="settings-alert success">{statusMsg}</div>}
      {error && <div className="settings-alert error">{error}</div>}

      <section className="sk-catalog" aria-labelledby="sk-catalog-title">
        <div className="sk-gate-head">
          <h2 id="sk-catalog-title" className="sk-section-title">
            {t("skills.catalogTitle", { ns: "settings" })}
          </h2>
          <p className="sk-section-desc">{t("skills.catalogDesc", { ns: "settings" })}</p>
        </div>
        {loading ? (
          <p className="sk-empty">{t("actions.loading", { ns: "common" })}</p>
        ) : skills.length === 0 ? (
          <p className="sk-empty">{t("skills.empty", { ns: "settings" })}</p>
        ) : (
          <ul className="sk-canister-grid">
            {skills.map((skill) => (
              <li key={skill.id} className={`sk-canister sk-canister--${skill.source || "builtin"}`}>
                <div className="sk-canister-sprocket" aria-hidden />
                <div className="sk-canister-body">
                  <div className="sk-canister-top">
                    <h3 className="sk-canister-title">{skill.title || skill.id}</h3>
                    <span className={`sk-source sk-source--${skill.source || "builtin"}`}>
                      {skill.source || "builtin"}
                    </span>
                  </div>
                  <p className="sk-canister-id">/{skill.id}</p>
                  {skill.description ? (
                    <p className="sk-canister-desc">{skill.description}</p>
                  ) : (
                    <p className="sk-canister-desc sk-muted">
                      {t("skills.noDescription", { ns: "settings" })}
                    </p>
                  )}
                  {skill.highlights && skill.highlights.length > 0 ? (
                    <ul className="sk-canister-effects">
                      {skill.highlights.map((h) => (
                        <li key={h}>{h}</li>
                      ))}
                    </ul>
                  ) : null}
                  {skill.aliases && skill.aliases.length > 0 && (
                    <p className="sk-aliases">
                      {t("skills.aliases", { ns: "settings" })}:{" "}
                      {skill.aliases.map((a) => `/${a}`).join(" · ")}
                    </p>
                  )}
                  <div className="sk-canister-foot">
                    {skill.deletable ? (
                      <button
                        type="button"
                        className="sk-delete-btn"
                        onClick={() => void handleDelete(skill.id)}
                      >
                        {t("skills.delete", { ns: "settings" })}
                      </button>
                    ) : (
                      <span className="sk-locked">
                        {t("skills.builtinLocked", { ns: "settings" })}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </AppShell>
  );
}
