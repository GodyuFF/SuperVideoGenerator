/**
 * 桌面打包版设置页：GitHub Releases 检查更新区块。
 */

import { useCallback, useEffect, useState } from "react";
import {
  checkDesktopUpdates,
  getDesktopUpdateState,
  getSvfDesktop,
  isPackagedDesktopApp,
} from "../../desktop/svfDesktop";
import type { DesktopUpdateState } from "../../desktop/types";

/** 设置页内嵌的桌面自动更新面板。 */
export function DesktopUpdateSection() {
  const [visible, setVisible] = useState(false);
  const [checking, setChecking] = useState(false);
  const [updateState, setUpdateState] = useState<DesktopUpdateState | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  /** 初始化可见性与当前更新状态。 */
  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const packaged = await isPackagedDesktopApp();
      if (cancelled) return;
      setVisible(packaged);
      if (!packaged) return;

      const state = await getDesktopUpdateState();
      if (!cancelled) {
        setUpdateState(state);
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  /** 订阅主进程推送的更新状态。 */
  useEffect(() => {
    const api = getSvfDesktop();
    if (!api || !visible) return undefined;
    return api.onUpdateState((state: DesktopUpdateState) => {
      setUpdateState(state);
    });
  }, [visible]);

  /** 手动检查 GitHub Releases 更新。 */
  const handleCheck = useCallback(async () => {
    const api = getSvfDesktop();
    if (!api) return;
    setChecking(true);
    setActionError(null);
    try {
      await checkDesktopUpdates();
      const state = await getDesktopUpdateState();
      if (state) {
        setUpdateState(state);
      }
    } catch (err) {
      setActionError((err as Error).message || "检查更新失败");
    } finally {
      setChecking(false);
    }
  }, []);

  /** 退出并安装已下载更新。 */
  const handleInstall = useCallback(async () => {
    const api = getSvfDesktop();
    if (!api) return;
    setActionError(null);
    const result = await api.quitAndInstall();
    if (!result.ok && result.message) {
      setActionError(result.message);
    }
  }, []);

  if (!visible) return null;

  const currentVersion = updateState?.currentVersion ?? "—";
  const canInstall = updateState?.status === "downloaded";
  const busy =
    checking || updateState?.status === "checking" || updateState?.status === "downloading";

  return (
    <section className="settings-desktop-update" aria-label="应用更新">
      <h2 className="settings-section-title">应用更新</h2>
      <p className="muted settings-intro">
        当前版本 {currentVersion}。桌面安装包仅从本仓库 GitHub Releases 获取更新，不支持自定义更新源。
      </p>
      {updateState?.message ? (
        <p className="field-hint" role="status">
          {updateState.message}
          {updateState.status === "downloading" && updateState.percent != null
            ? `（${Math.round(updateState.percent)}%）`
            : null}
        </p>
      ) : null}
      {actionError ? <p className="board-error">{actionError}</p> : null}
      <div className="settings-actions" style={{ marginTop: 0 }}>
        <button type="button" disabled={busy} onClick={() => void handleCheck()}>
          {busy ? "检查中…" : "检查更新"}
        </button>
        {canInstall ? (
          <button type="button" className="btn-secondary" onClick={() => void handleInstall()}>
            立即重启并安装
          </button>
        ) : null}
      </div>
    </section>
  );
}
