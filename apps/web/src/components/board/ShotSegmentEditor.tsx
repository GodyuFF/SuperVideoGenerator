/**
 * 镜内多轨编辑：配音幕（角色语音）+ 句级字幕 + 子镜（仅挂接 frame/video_clip）。
 */

import { useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { PatchVideoPlanShotBody, VideoPlanShot } from "../../types/videoPlan";
import { fetchSubtitlesFromVoiceAudio } from "../../lib/shotSubtitlesFromVoice";
import {
  applyMediaDurationToVoiceActs,
  buildShotPatchFromSegments,
  newSubShot,
  newSubtitleLine,
  newVoiceAct,
  parseSubShotsFromPlan,
  parseSubtitlesFromPlan,
  parseVoiceActsFromPlan,
  quantizeDurationMs,
  resolveShotDurationFromSegments,
  validateShotSegmentEdits,
  type MediaMetaInfo,
  type ShotSubShotView,
  type ShotSubtitleView,
  type ShotVoiceActView,
  type StyleVideoGenMode,
} from "../../utils/shotSegmentUtils";
import { ShotSubShotCard } from "./ShotSubShotCard";
import { ShotVoiceActCard } from "./ShotVoiceActCard";
import { SubtitleSegmentEditor } from "./SubtitleSegmentEditor";
import { useVoiceActCharacters } from "../../hooks/useVoiceActCharacters";

interface ShotSegmentEditorProps {
  projectId: string;
  scriptId: string;
  shot: VideoPlanShot;
  saving?: boolean;
  mediaLinkById?: Record<string, string>;
  /** media_id → 类型/名称，用于画面槽展示孤立图片素材。 */
  mediaMetaById?: Record<string, MediaMetaInfo>;
  /** media_id → 实测时长（毫秒），用于自动推算镜时长。 */
  mediaDurationById?: Record<string, number>;
  onOpenEditTimeline?: () => void;
  onSave: (body: PatchVideoPlanShotBody) => Promise<void>;
  onCancel: () => void;
  styleVideoModes?: StyleVideoGenMode[];
  /** 上传配音后刷新 video-plan 与媒体索引。 */
  onPlanRefresh?: () => Promise<void>;
}

/** 分镜镜内多轨分段编辑。 */
export function ShotSegmentEditor({
  projectId,
  scriptId,
  shot,
  saving,
  mediaLinkById,
  mediaMetaById,
  mediaDurationById,
  onOpenEditTimeline,
  onSave,
  onCancel,
  styleVideoModes,
  onPlanRefresh,
}: ShotSegmentEditorProps) {
  const { t } = useAppTranslation("board");
  const { characters, loading: charactersLoading } = useVoiceActCharacters(projectId, scriptId);
  const [reviewNote, setReviewNote] = useState(shot.review_note ?? "");
  const [voiceActs, setVoiceActs] = useState<ShotVoiceActView[]>([]);
  const [subShots, setSubShots] = useState<ShotSubShotView[]>([]);
  const [subtitles, setSubtitles] = useState<ShotSubtitleView[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [generatingSubs, setGeneratingSubs] = useState(false);

  /** 仅切换镜头时重置表单；避免 video-plan 引用刷新冲掉正在编辑的配音文案。 */
  useEffect(() => {
    setReviewNote(shot.review_note ?? "");
    const acts = applyMediaDurationToVoiceActs(
      parseVoiceActsFromPlan(shot, projectId, scriptId, mediaLinkById),
      mediaDurationById,
    );
    const subs = parseSubShotsFromPlan(
      shot,
      projectId,
      scriptId,
      mediaLinkById,
      mediaMetaById,
    );
    setVoiceActs(acts);
    setSubShots(subs.length ? subs : [newSubShot(shot.duration_ms ?? 3000)]);
    setSubtitles(parseSubtitlesFromPlan(shot));
    setFormError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 刻意只随 shot.id 重置，保留编辑中本地状态
  }, [shot.id, projectId, scriptId]);

  /** 媒体索引更新时只回填预览 URL / 元数据，不改文案与时间码。 */
  useEffect(() => {
    if (!mediaLinkById && !mediaMetaById) return;
    setVoiceActs((prev) => {
      if (!mediaLinkById) return prev;
      let changed = false;
      const next = prev.map((a) => {
        const mid = (a.mediaId ?? "").trim();
        if (!mid) return a;
        const url = mediaLinkById[mid];
        if (!url || url === a.audioUrl) return a;
        changed = true;
        return { ...a, audioUrl: url };
      });
      return changed ? next : prev;
    });
    setSubShots((prev) => {
      let changed = false;
      const next = prev.map((s) => {
        const imageMediaId = (s.imageMediaId ?? "").trim();
        const videoClipMediaId = (s.videoClipMediaId ?? "").trim();
        const imageUrl =
          mediaLinkById && imageMediaId ? mediaLinkById[imageMediaId] : undefined;
        const videoClipUrl =
          mediaLinkById && videoClipMediaId ? mediaLinkById[videoClipMediaId] : undefined;
        const nextImage = imageUrl && imageUrl !== s.imageUrl ? imageUrl : s.imageUrl;
        const nextVideo =
          videoClipUrl && videoClipUrl !== s.videoClipUrl ? videoClipUrl : s.videoClipUrl;
        let imagesChanged = false;
        const nextImages = (s.images ?? []).map((img) => {
          const mid = (img.imageMediaId ?? "").trim();
          const url = mediaLinkById && mid ? mediaLinkById[mid] : undefined;
          const meta = mediaMetaById && mid ? mediaMetaById[mid] : undefined;
          const nextUrl = url && url !== img.imageUrl ? url : img.imageUrl;
          const nextType = meta?.type ?? img.mediaType;
          const nextName = meta?.name || img.mediaName;
          if (
            nextUrl === img.imageUrl &&
            nextType === img.mediaType &&
            nextName === img.mediaName
          ) {
            return img;
          }
          imagesChanged = true;
          return { ...img, imageUrl: nextUrl, mediaType: nextType, mediaName: nextName };
        });
        if (
          nextImage === s.imageUrl &&
          nextVideo === s.videoClipUrl &&
          !imagesChanged
        ) {
          return s;
        }
        changed = true;
        return {
          ...s,
          imageUrl: nextImage,
          videoClipUrl: nextVideo,
          images: imagesChanged ? nextImages : s.images,
        };
      });
      return changed ? next : prev;
    });
  }, [mediaLinkById, mediaMetaById]);

  /** 媒体时长到齐后，按实测配音长度延长幕终点。 */
  useEffect(() => {
    if (!mediaDurationById) return;
    setVoiceActs((prev) => applyMediaDurationToVoiceActs(prev, mediaDurationById));
  }, [mediaDurationById]);

  const resolvedDuration = useMemo(
    () =>
      resolveShotDurationFromSegments({
        planDurationMs: shot.duration_ms ?? 3000,
        voiceActs,
        subShots,
        subtitles,
        mediaDurationById,
      }),
    [shot.duration_ms, voiceActs, subShots, subtitles, mediaDurationById],
  );
  const durationMs = Math.max(500, quantizeDurationMs(resolvedDuration.durationMs));

  const updateVoice = (id: string, patch: Partial<ShotVoiceActView>) => {
    setVoiceActs((prev) => prev.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  };

  const updateSubShot = (id: string, patch: Partial<ShotSubShotView>) => {
    setSubShots((prev) => prev.map((v) => (v.id === id ? { ...v, ...patch } : v)));
  };

  /** 从已绑定配音音频生成句级字幕（TTS cues / ASR，非配音幕文案）。 */
  const handleGenerateSubtitlesFromVoice = () => {
    const hasBoundAudio = voiceActs.some((a) => Boolean((a.mediaId ?? "").trim()));
    if (!hasBoundAudio) {
      setFormError(t("storyboard.subtitle.generateEmpty"));
      return;
    }
    if (subtitles.length > 0 && !window.confirm(t("storyboard.subtitle.generateConfirm"))) {
      return;
    }
    setFormError(null);
    setGeneratingSubs(true);
    void (async () => {
      try {
        const rows = await fetchSubtitlesFromVoiceAudio(projectId, scriptId, shot.id);
        if (rows.length === 0) {
          setFormError(t("storyboard.subtitle.generateNoCues"));
          return;
        }
        setSubtitles(
          rows.map((row, idx) => ({
            id: row.id?.trim() || `ssub-audio-${idx}`,
            startMs: Number(row.start_ms ?? 0),
            endMs: Number(row.end_ms ?? 0) || durationMs,
            text: String(row.text ?? "").trim(),
            character: String(row.character ?? "").trim(),
            color: String(row.color ?? "").trim(),
          })).filter((s) => s.text),
        );
      } catch (err) {
        setFormError(
          err instanceof Error ? err.message : t("storyboard.subtitle.generateFailed"),
        );
      } finally {
        setGeneratingSubs(false);
      }
    })();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errKey = validateShotSegmentEdits(durationMs, voiceActs, subShots, subtitles);
    if (errKey) {
      setFormError(t(errKey));
      return;
    }
    setFormError(null);
    await onSave(
      buildShotPatchFromSegments(shot, {
        durationMs,
        reviewNote,
        voiceActs,
        subShots,
        subtitles,
      }),
    );
  };

  const sourceLabel = t(`storyboard.durationSource.${resolvedDuration.source}`);

  return (
    <form className="shot-segment-editor" onSubmit={(e) => void handleSubmit(e)}>
      <div className="shot-editor-field">
        <label htmlFor="shot-duration">{t("storyboard.sectionDuration")}</label>
        <input
          id="shot-duration"
          type="number"
          readOnly
          value={durationMs}
          title={t("storyboard.durationAutoHint")}
        />
        <p className="muted shot-segment-editor__hint">
          {t("storyboard.durationAutoLine", {
            sec: (durationMs / 1000).toFixed(1),
            source: sourceLabel,
          })}
        </p>
      </div>

      <div className="shot-editor-field">
        <label htmlFor="shot-display">{t("storyboard.sectionDisplay")}</label>
        <textarea
          id="shot-display"
          rows={2}
          value={reviewNote}
          onChange={(e) => setReviewNote(e.target.value)}
        />
      </div>

      <div className="shot-segment-editor__section">
        <div className="shot-segment-editor__section-head">
          <h4>{t("storyboard.voiceAct.sectionTitle")}</h4>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() =>
              setVoiceActs((prev) => [
                ...prev,
                newVoiceAct(durationMs, prev[prev.length - 1]?.endMs ?? 0),
              ])
            }
          >
            {t("storyboard.voiceAct.add")}
          </button>
        </div>
        <div className="shot-segment-editor__list">
          {voiceActs.map((act, idx) => (
            <ShotVoiceActCard
              key={act.id}
              act={act}
              index={idx}
              projectId={projectId}
              scriptId={scriptId}
              shotId={shot.id}
              editable
              characterOptions={characters}
              charactersLoading={charactersLoading}
              onChange={(patch) => updateVoice(act.id, patch)}
              onRemove={() => setVoiceActs((prev) => prev.filter((a) => a.id !== act.id))}
              onAudioSynced={() => void onPlanRefresh?.()}
            />
          ))}
        </div>
      </div>

      <div className="shot-segment-editor__section">
        <div className="shot-segment-editor__section-head">
          <h4>{t("storyboard.subtitle.title")}</h4>
          <div className="shot-segment-editor__section-actions">
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={handleGenerateSubtitlesFromVoice}
              disabled={generatingSubs || !voiceActs.some((a) => Boolean((a.mediaId ?? "").trim()))}
              title={t("storyboard.subtitle.generateFromVoiceHint")}
            >
              {generatingSubs
                ? t("storyboard.subtitle.generating")
                : t("storyboard.subtitle.generateFromVoice")}
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() =>
                setSubtitles((prev) => [
                  ...prev,
                  newSubtitleLine(durationMs, prev[prev.length - 1]?.endMs ?? 0),
                ])
              }
            >
              {t("storyboard.subtitle.add")}
            </button>
          </div>
        </div>
        <p className="muted shot-segment-editor__hint">{t("storyboard.subtitle.editHint")}</p>
        <SubtitleSegmentEditor
          durationMs={durationMs}
          subtitles={subtitles}
          onChange={setSubtitles}
        />
      </div>

      <div className="shot-segment-editor__section">
        <div className="shot-segment-editor__section-head">
          <h4>{t("storyboard.subShot.sectionTitle")}</h4>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() =>
              setSubShots((prev) => [
                ...prev,
                newSubShot(durationMs, prev[prev.length - 1]?.endMs ?? 0),
              ])
            }
          >
            {t("storyboard.subShot.add")}
          </button>
        </div>
        <div className="shot-segment-editor__list">
          {subShots.map((vis, idx) => (
            <ShotSubShotCard
              key={vis.id}
              visual={vis}
              index={idx}
              projectId={projectId}
              scriptId={scriptId}
              shotId={shot.id}
              editable
              onChange={(patch) => updateSubShot(vis.id, patch)}
              onOpenEditTimeline={onOpenEditTimeline}
              voiceActs={voiceActs}
              styleVideoModes={styleVideoModes}
              onRemove={
                subShots.length > 1
                  ? () => setSubShots((prev) => prev.filter((v) => v.id !== vis.id))
                  : undefined
              }
            />
          ))}
        </div>
      </div>

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
