/**
 * 分镜单镜编辑表单：旁白、运镜、复核说明与元素引用。
 */

import { useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { PatchVideoPlanShotBody, VideoPlanShot } from "../../types/videoPlan";
import {
  quantizeDurationMs,
  resolveShotDisplayDurationFromPlan,
} from "../../utils/shotSegmentUtils";
import {
  buildShotPatchFromEdits,
  shotCameraMotion,
  shotElementRefs,
  shotVoiceText,
} from "../../utils/shotTrackUtils";
import { AssetRefPicker } from "./AssetRefPicker";

const API = "/api";

interface MotionOption {
  id: string;
  label?: string;
}

interface ShotEditorFormProps {
  projectId: string;
  scriptId: string;
  shot: VideoPlanShot;
  saving?: boolean;
  onSave: (body: PatchVideoPlanShotBody) => Promise<void>;
  onCancel: () => void;
}

/** 分镜镜头完整编辑表单（镜内多轨 patch）。 */
export function ShotEditorForm({
  projectId,
  scriptId,
  shot,
  saving,
  onSave,
  onCancel,
}: ShotEditorFormProps) {
  const { t } = useAppTranslation("board");
  const [narration, setNarration] = useState(shotVoiceText(shot));
  const [cameraMotion, setCameraMotion] = useState(shotCameraMotion(shot));
  const [reviewNote, setReviewNote] = useState(shot.review_note ?? "");
  const [elementRefs, setElementRefs] = useState<Record<string, string[]>>(
    shotElementRefs(shot),
  );
  const [motions, setMotions] = useState<MotionOption[]>([]);
  const [formError, setFormError] = useState<string | null>(null);

  const resolvedDuration = useMemo(
    () => resolveShotDisplayDurationFromPlan(shot),
    [shot],
  );
  const durationMs = Math.max(500, quantizeDurationMs(resolvedDuration.durationMs));

  useEffect(() => {
    setNarration(shotVoiceText(shot));
    setCameraMotion(shotCameraMotion(shot));
    setReviewNote(shot.review_note ?? "");
    setElementRefs(shotElementRefs(shot));
  }, [shot]);

  useEffect(() => {
    void fetch(`${API}/edit/capabilities`)
      .then((r) => r.json())
      .then((data) => {
        const raw = (data.motions ?? []) as Array<{ id?: string; label?: string } | string>;
        setMotions(
          raw
            .map((m) =>
              typeof m === "string"
                ? { id: m, label: m }
                : { id: m.id ?? "", label: m.label ?? m.id },
            )
            .filter((m) => m.id),
        );
      })
      .catch(() => setMotions([{ id: "static", label: "static" }]));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!narration.trim()) {
      setFormError("旁白不能为空");
      return;
    }
    setFormError(null);
    await onSave(
      buildShotPatchFromEdits(shot, {
        narration,
        cameraMotion,
        reviewNote,
        durationMs,
        elementRefs,
      }),
    );
  };

  return (
    <form className="shot-editor-form" onSubmit={(e) => void handleSubmit(e)}>
      <div className="shot-editor-field">
        <label htmlFor="shot-narration">{t("storyboard.sectionNarration")}</label>
        <textarea
          id="shot-narration"
          rows={4}
          value={narration}
          onChange={(e) => setNarration(e.target.value)}
        />
      </div>

      <div className="shot-editor-field">
        <label htmlFor="shot-duration">{t("storyboard.sectionDuration")}</label>
        <input
          id="shot-duration"
          type="number"
          readOnly
          value={durationMs}
          title={t("storyboard.durationAutoHint")}
        />
        <p className="muted">
          {t("storyboard.durationAutoLine", {
            sec: (durationMs / 1000).toFixed(1),
            source: t(`storyboard.durationSource.${resolvedDuration.source}`),
          })}
        </p>
      </div>

      <div className="shot-editor-field">
        <label htmlFor="shot-motion">{t("storyboard.sectionMotion")}</label>
        <select
          id="shot-motion"
          value={cameraMotion}
          onChange={(e) => setCameraMotion(e.target.value)}
        >
          {motions.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label ?? m.id}
            </option>
          ))}
        </select>
      </div>

      <div className="shot-editor-field">
        <label htmlFor="shot-display">{t("storyboard.sectionDisplay")}</label>
        <textarea
          id="shot-display"
          rows={3}
          value={reviewNote}
          onChange={(e) => setReviewNote(e.target.value)}
        />
      </div>

      <AssetRefPicker
        projectId={projectId}
        scriptId={scriptId}
        value={elementRefs}
        onChange={setElementRefs}
      />

      {formError ? <p className="form-error">{formError}</p> : null}

      <div className="shot-editor-actions">
        <button type="button" className="btn-secondary" onClick={onCancel} disabled={saving}>
          {t("storyboard.edit.cancel")}
        </button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? t("storyboard.edit.saving") : t("storyboard.edit.save")}
        </button>
      </div>
    </form>
  );
}
