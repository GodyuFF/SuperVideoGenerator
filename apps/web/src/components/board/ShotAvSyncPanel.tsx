/**
 * 分镜抽屉「音画协调」面板：展示偏差、主轨策略与 Tier2 可选方案。
 */

import { useCallback, useEffect, useState } from "react";
import type { AvSyncAction, VideoPlanShot } from "../../types/videoPlan";

export type ShotSyncPolicy = "narration_master" | "visual_master" | "balanced";

interface AvSyncResultRow {
  shot_id?: string;
  status?: string;
  tier?: number;
  policy?: string;
  delta_ms?: number;
  probe?: {
    tts_ms?: number;
    video_ms?: number;
    slot_ms?: number;
    visual_ms?: number;
  };
  options?: AvSyncAction[];
  applied?: AvSyncAction;
  regen_reason?: Record<string, unknown>;
}

interface ShotAvSyncPanelProps {
  /** 当前镜计划稿数据。 */
  planShot: VideoPlanShot | null | undefined;
  shotId: string;
  /** 是否允许写入（编辑模式）。 */
  enabled?: boolean;
  /** 分析音画；默认 analyze_only。 */
  onAnalyze?: (opts?: {
    mode?: "analyze_only" | "hybrid" | "auto_only";
    shotIds?: string[];
  }) => Promise<Record<string, unknown>>;
  /** 应用单条方案。 */
  onApplyAction?: (
    shotId: string,
    action: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>;
  /** 更新主轨策略。 */
  onPatchPolicy?: (body: {
    sync_policy?: ShotSyncPolicy;
    lip_sync_required?: boolean;
  }) => Promise<void>;
}

const POLICY_LABELS: Record<ShotSyncPolicy, string> = {
  narration_master: "配音为主",
  visual_master: "画面为主",
  balanced: "双向微调",
};

/** 分镜音画时长协调面板。 */
export function ShotAvSyncPanel({
  planShot,
  shotId,
  enabled = false,
  onAnalyze,
  onApplyAction,
  onPatchPolicy,
}: ShotAvSyncPanelProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AvSyncResultRow | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const proposed = (planShot?.proposed_sync_actions ??
    analysis?.options ??
    []) as AvSyncAction[];
  const policy = (planShot?.sync_policy ??
    analysis?.policy ??
    "narration_master") as ShotSyncPolicy;
  const deltaMs = analysis?.delta_ms ?? 0;
  const tier = analysis?.tier ?? (proposed.length ? 2 : 0);

  /** 拉取当前镜分析。 */
  const runAnalyze = useCallback(async () => {
    if (!onAnalyze) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const raw = await onAnalyze({
        mode: "analyze_only",
        shotIds: [shotId],
      });
      const results = (raw.results as AvSyncResultRow[]) || [];
      const row = results.find((r) => r.shot_id === shotId) || results[0] || null;
      setAnalysis(row);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [onAnalyze, shotId]);

  useEffect(() => {
    void runAnalyze();
  }, [runAnalyze]);

  /** 切换主轨策略。 */
  const handlePolicyChange = async (next: ShotSyncPolicy) => {
    if (!onPatchPolicy || !enabled) return;
    setBusy(true);
    setError(null);
    try {
      await onPatchPolicy({ sync_policy: next });
      setMsg(`已切换主轨：${POLICY_LABELS[next]}`);
      await runAnalyze();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  /** 一键应用方案。 */
  const handleApply = async (action: AvSyncAction) => {
    if (!onApplyAction || !enabled) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await onApplyAction(shotId, { ...action });
      setMsg(`已应用：${action.label || action.kind}`);
      await runAnalyze();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  /** 自动修复（hybrid）。 */
  const handleAutoFix = async () => {
    if (!onAnalyze || !enabled) return;
    setBusy(true);
    setError(null);
    try {
      const raw = await onAnalyze({ mode: "hybrid", shotIds: [shotId] });
      const results = (raw.results as AvSyncResultRow[]) || [];
      const row = results.find((r) => r.shot_id === shotId) || results[0] || null;
      setAnalysis(row);
      setMsg(
        row?.status === "auto_applied"
          ? `已自动修复${row.applied?.label ? `：${row.applied.label}` : ""}`
          : row?.status === "ok"
            ? "音画已对齐"
            : `状态：${row?.status || "unknown"}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const probe = analysis?.probe;
  const showMismatch = Math.abs(deltaMs) > 500 || proposed.length > 0;

  return (
    <section className="asset-detail-section shot-av-sync-panel">
      <div className="shot-detail-drawer__section-head">
        <h4>音画协调</h4>
        <div className="shot-av-sync-panel__actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={busy || !onAnalyze}
            onClick={() => void runAnalyze()}
          >
            刷新分析
          </button>
          {enabled && onAnalyze ? (
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={busy}
              onClick={() => void handleAutoFix()}
            >
              自动修复
            </button>
          ) : null}
        </div>
      </div>

      <div className="shot-av-sync-panel__policy">
        <span className="muted">主轨策略</span>
        <select
          value={policy}
          disabled={!enabled || busy || !onPatchPolicy}
          onChange={(e) =>
            void handlePolicyChange(e.target.value as ShotSyncPolicy)
          }
        >
          {(Object.keys(POLICY_LABELS) as ShotSyncPolicy[]).map((k) => (
            <option key={k} value={k}>
              {POLICY_LABELS[k]}
            </option>
          ))}
        </select>
        {planShot?.lip_sync_required ? (
          <span className="storyboard-status-badge storyboard-status-badge--warn">
            口型同步
          </span>
        ) : null}
      </div>

      {probe ? (
        <p className="muted shot-av-sync-panel__probe tabular-nums">
          配音 {(probe.tts_ms ?? 0) / 1000}s · 视频 {(probe.video_ms ?? 0) / 1000}s ·
          槽位 {(probe.slot_ms ?? 0) / 1000}s
          {showMismatch ? (
            <>
              {" "}
              · 偏差 {(deltaMs / 1000).toFixed(2)}s · Tier {tier}
            </>
          ) : (
            " · 已对齐"
          )}
        </p>
      ) : (
        <p className="muted">分析中…</p>
      )}

      {planShot?.regen_reason ? (
        <p className="shot-av-sync-panel__regen muted">
          打回：{planShot.regen_reason.slice(0, 160)}
          {planShot.regen_reason.length > 160 ? "…" : ""}
        </p>
      ) : null}

      {proposed.length > 0 ? (
        <ul className="shot-av-sync-panel__options">
          {proposed.map((opt, idx) => (
            <li key={`${opt.kind}-${idx}`}>
              <div>
                <strong>{opt.label || opt.kind}</strong>
                {opt.description ? (
                  <p className="muted">{opt.description}</p>
                ) : null}
              </div>
              {enabled && onApplyAction ? (
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  disabled={busy}
                  onClick={() => void handleApply(opt)}
                >
                  应用
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {msg ? <p className="shot-av-sync-panel__msg">{msg}</p> : null}
      {error ? <p className="form-error">{error}</p> : null}
    </section>
  );
}
