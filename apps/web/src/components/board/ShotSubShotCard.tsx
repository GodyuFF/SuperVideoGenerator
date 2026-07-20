/**
 * 单条子镜卡片：可挂接多画面 / 多视频（各带时段），并提供剪辑轴入口。
 * 子镜槽位不挂角色资产；角色仅出现在配音幕（角色语音）。
 */

import { useMemo, useState } from "react";
import { AssetImagePreview } from "../AssetImagePreview";
import { AssetRegenerateButton } from "../AssetRegenerateButton";
import { MediaPreview } from "../MediaPreview";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { formatMs } from "./storyboardShared";
import { ShotSubShotFramePicker } from "./ShotSubShotFramePicker";
import {
  type ProduceMode,
  type ShotSubShotFrameView,
  type ShotSubShotView,
  type ShotVoiceActView,
  type StyleVideoGenMode,
  produceModeToVideoGenMode,
  resolveSubShotDisplayRange,
  subShotHasBoundTimeline,
  subShotHasBoundVideo,
  syncSubShotPrimaryImageFields,
} from "../../utils/shotSegmentUtils";
import { ShotSubShotVideoPicker } from "./ShotSubShotVideoPicker";
import {
  SubShotMediaLane,
  type SubShotMediaLaneSegment,
} from "./SubShotMediaLane";

interface ShotSubShotCardProps {
  visual: ShotSubShotView;
  index: number;
  projectId: string;
  scriptId: string;
  shotId: string;
  selected?: boolean;
  editable?: boolean;
  regenerateEnabled?: boolean;
  onSelect?: () => void;
  onChange?: (patch: Partial<ShotSubShotView>) => void;
  onRemove?: () => void;
  onNavigateAsset?: (id: string, kind: string) => void;
  onRegenerateDone?: () => void;
  /** 跳转全片剪辑 Tab（剪辑轴特殊编辑模式）。 */
  onOpenEditTimeline?: () => void;
  /** 镜内配音幕，用于子镜展示时段优先级解析。 */
  voiceActs?: ShotVoiceActView[];
  /** 当前剧本视频风格允许的 AI 生视频子模式。 */
  styleVideoModes?: StyleVideoGenMode[];
}

const PRODUCE_MODE_I18N: Record<ProduceMode, string> = {
  still: "storyboard.subShot.produceModeStill",
  text2video: "storyboard.subShot.produceModeText2Video",
  img2video: "storyboard.subShot.produceModeImg2Video",
};

/** 子镜是否有关联画面。 */
function hasFrameBinding(visual: ShotSubShotView): boolean {
  if (visual.images?.some((i) => i.frameAssetId || i.imageUrl || i.imageMediaId)) {
    return true;
  }
  return Boolean(visual.frameAssetId || visual.imageUrl || visual.imageMediaId);
}

/** 截断意图说明，用于卡片只读一行摘要。 */
function truncateRationale(text: string, maxLen = 80): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLen) return trimmed;
  return `${trimmed.slice(0, maxLen)}…`;
}

/** 画面时段是否与所属子镜时段相同（缺省时段视为相同）。 */
function imageTimingMatchesSub(
  frame: Pick<ShotSubShotFrameView, "startMs" | "endMs">,
  subStartMs: number,
  subEndMs: number,
): boolean {
  const start = frame.startMs ?? subStartMs;
  const end = frame.endMs ?? subEndMs;
  return start === subStartMs && end === subEndMs;
}

/** 子镜只读/编辑卡片。 */
export function ShotSubShotCard({
  visual,
  index,
  projectId,
  scriptId,
  shotId,
  selected,
  editable,
  regenerateEnabled,
  onSelect,
  onChange,
  onRemove,
  onNavigateAsset,
  onRegenerateDone,
  onOpenEditTimeline,
  voiceActs = [],
  styleVideoModes,
}: ShotSubShotCardProps) {
  const { t } = useAppTranslation("board");
  const displayRange = resolveSubShotDisplayRange(visual, voiceActs);
  void styleVideoModes;
  const [laneFocusId, setLaneFocusId] = useState<string | null>(null);

  /** 产出意图文案。 */
  const produceModeLabel = (mode: ProduceMode) => t(PRODUCE_MODE_I18N[mode]);

  /** 编辑态始终可挂多画面/多视频；只读按是否已挂接展示。 */
  const showFrameSection = Boolean(editable || hasFrameBinding(visual));
  const showVideoSection = Boolean(editable || subShotHasBoundVideo(visual));
  const showFrameRegen = Boolean(regenerateEnabled && !editable && hasFrameBinding(visual));
  const showVideoRegen = Boolean(regenerateEnabled && !editable && subShotHasBoundVideo(visual));

  /** 子镜内画面/视频时段条数据。 */
  const laneSegments = useMemo((): SubShotMediaLaneSegment[] => {
    const frames: SubShotMediaLaneSegment[] = (visual.images ?? []).map((img, idx) => ({
      id: img.id,
      startMs: img.startMs ?? visual.startMs,
      endMs: img.endMs ?? visual.endMs,
      label: img.frameName || img.frameAssetId || t("storyboard.subShot.frameItem", { index: idx + 1 }),
      kind: "frame",
    }));
    const videos: SubShotMediaLaneSegment[] = (visual.videos ?? []).map((vid, idx) => ({
      id: vid.id,
      startMs: vid.startMs,
      endMs: vid.endMs,
      label:
        vid.videoClipName ||
        vid.videoClipAssetId ||
        t("storyboard.subShot.videoItem", { index: idx + 1 }),
      kind: "video",
    }));
    return [...frames, ...videos];
  }, [visual.images, visual.videos, visual.startMs, visual.endMs, t]);
  const showTimeline = subShotHasBoundTimeline(visual);
  const showDescription = editable || Boolean(visual.description.trim());
  const showDurationSourceInHeader =
    editable ||
    displayRange.source === "plan" ||
    displayRange.source === "voice";
  const produceRationale = (visual.produceRationale ?? "").trim();

  /** 只读态单张画面的时段文案。 */
  const imageTimingText = (frame: Pick<ShotSubShotFrameView, "startMs" | "endMs">) => {
    if (imageTimingMatchesSub(frame, visual.startMs, visual.endMs)) {
      return t("storyboard.subShot.imageTimingSameAsSub");
    }
    const start = frame.startMs ?? visual.startMs;
    const end = frame.endMs ?? visual.endMs;
    return t("storyboard.subShot.imageTiming", {
      start: formatMs(start),
      end: formatMs(end),
    });
  };

  return (
    <article
      className={`shot-segment-card shot-visual-card${selected ? " is-selected" : ""}${editable ? " shot-visual-card--editable" : ""}`}
      onClick={editable ? undefined : onSelect}
      onKeyDown={
        editable || !onSelect
          ? undefined
          : (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect();
              }
            }
      }
      role={editable ? undefined : onSelect ? "button" : undefined}
      tabIndex={editable ? undefined : onSelect ? 0 : undefined}
    >
      <header className="shot-segment-card__head">
        <span className="shot-segment-card__eyebrow">
          {t("storyboard.subShot.title", { index: index + 1 })}
        </span>
        <span className="shot-segment-card__time tabular-nums">
          {editable ? (
            <>
              {formatMs(visual.startMs)}–{formatMs(visual.endMs)}
            </>
          ) : (
            <>
              {formatMs(visual.startMs)}–{formatMs(visual.endMs)}
              {showDurationSourceInHeader &&
              (displayRange.startMs !== visual.startMs ||
                displayRange.endMs !== visual.endMs) ? (
                <span className="muted">
                  {" "}
                  · {t("storyboard.subShot.mediaRange", {
                    start: formatMs(displayRange.startMs),
                    end: formatMs(displayRange.endMs),
                  })}
                </span>
              ) : null}
            </>
          )}
        </span>
        <span className="meta-chip">{produceModeLabel(visual.produceMode)}</span>
        <span className="meta-chip shot-segment-card__motion">{visual.cameraMotion}</span>
        {editable && onRemove ? (
          <button
            type="button"
            className="btn-secondary btn-sm shot-segment-card__remove"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
          >
            {t("storyboard.subShot.remove")}
          </button>
        ) : null}
      </header>

      {!editable && produceRationale ? (
        <p className="muted shot-segment-card__produce-rationale" title={produceRationale}>
          {truncateRationale(produceRationale)}
        </p>
      ) : null}

      {editable && onChange ? (
        <div className="shot-segment-card__fields" onClick={(e) => e.stopPropagation()}>
          <label className="shot-segment-field">
            <span>{t("storyboard.subShot.startMs")}</span>
            <input
              type="number"
              min={0}
              value={visual.startMs}
              onChange={(e) => onChange({ startMs: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="shot-segment-field">
            <span>{t("storyboard.subShot.endMs")}</span>
            <input
              type="number"
              min={0}
              value={visual.endMs}
              onChange={(e) => onChange({ endMs: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.sectionMotion")}</span>
            <input
              value={visual.cameraMotion}
              onChange={(e) => onChange({ cameraMotion: e.target.value })}
            />
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.subShot.description")}</span>
            <textarea
              rows={2}
              value={visual.description}
              onChange={(e) => onChange({ description: e.target.value })}
            />
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.subShot.produceMode")}</span>
            <select
              value={visual.produceMode}
              onChange={(e) => {
                const produceMode = e.target.value as ProduceMode;
                onChange({
                  produceMode,
                  videoGenMode: produceModeToVideoGenMode(produceMode),
                });
              }}
            >
              <option value="still">{t("storyboard.subShot.produceModeStill")}</option>
              <option value="text2video">{t("storyboard.subShot.produceModeText2Video")}</option>
              <option value="img2video">{t("storyboard.subShot.produceModeImg2Video")}</option>
            </select>
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.subShot.produceRationale")}</span>
            <input
              value={visual.produceRationale ?? ""}
              onChange={(e) => onChange({ produceRationale: e.target.value })}
              placeholder={t("storyboard.subShot.produceRationale")}
            />
          </label>

          <SubShotMediaLane
            subStartMs={visual.startMs}
            subEndMs={visual.endMs}
            segments={laneSegments}
            selectedId={laneFocusId}
            onSelect={(id) => {
              setLaneFocusId(id);
              const el =
                document.getElementById(`subshot-frame-${id}`) ??
                document.getElementById(`subshot-video-${id}`);
              el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
            }}
          />

          <section className="shot-subshot-content shot-subshot-content--frame">
            <ShotSubShotFramePicker
              projectId={projectId}
              scriptId={scriptId}
              shotId={shotId}
              images={visual.images ?? []}
              subShotStartMs={visual.startMs}
              subShotEndMs={visual.endMs}
              highlightSlotId={laneFocusId}
              onImagesChange={(images) =>
                onChange({
                  images,
                  ...syncSubShotPrimaryImageFields(images),
                  elementRefs: images[0]?.elementRefs ?? visual.elementRefs,
                })
              }
              onRegenerateDone={onRegenerateDone}
            />
          </section>

          <ShotSubShotVideoPicker
            projectId={projectId}
            scriptId={scriptId}
            shotId={shotId}
            subShotIdx={index}
            videos={visual.videos}
            subShotStartMs={visual.startMs}
            subShotEndMs={visual.endMs}
            highlightSlotId={laneFocusId}
            onChange={(videos) => onChange({ videos })}
            onRegenerateDone={onRegenerateDone}
          />

          {showTimeline && visual.timelineClip ? (
            <section className="shot-subshot-content shot-subshot-content--timeline">
              <div className="shot-subshot-content__head">
                <span className="shot-subshot-content__eyebrow">
                  {t("storyboard.subShot.timelineSection")}
                </span>
              </div>
              <p className="muted tabular-nums">
                {formatMs(visual.timelineClip.startMs)}–{formatMs(visual.timelineClip.endMs)}
              </p>
              {visual.timelineClip.url ? (
                <MediaPreview
                  kind="video"
                  url={visual.timelineClip.url}
                  label={t("storyboard.subShot.timelinePreview")}
                  projectId={projectId}
                  scriptId={scriptId}
                />
              ) : null}
              {onOpenEditTimeline ? (
                <button type="button" className="btn-secondary btn-sm" onClick={onOpenEditTimeline}>
                  {t("storyboard.subShot.openEditTimeline")}
                </button>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : (
        <>
          {showDescription ? (
            <p className="shot-segment-card__body">{visual.description}</p>
          ) : null}

          {(showFrameSection || showFrameRegen) ? (
            <section className="shot-subshot-content shot-subshot-content--frame">
              <span className="shot-subshot-content__eyebrow">
                {t("storyboard.subShot.frameSection")}
              </span>
              {showFrameSection ? (
                <ul className="shot-subshot-frame-list shot-subshot-frame-list--readonly">
                  {(visual.images?.length
                    ? visual.images
                    : visual.imageUrl || visual.frameAssetId || visual.imageMediaId
                      ? [
                          {
                            id: "ssi-readonly-0",
                            frameAssetId: visual.frameAssetId,
                            imageUrl: visual.imageUrl,
                            imageMediaId: visual.imageMediaId,
                            frameName: undefined,
                            sourceMediaIds: [],
                            startMs: visual.startMs,
                            endMs: visual.endMs,
                          } satisfies ShotSubShotFrameView,
                        ]
                      : []
                  ).map((frame, frameIdx) => {
                    const isVideoMedia = frame.mediaType === "video";
                    const canShowImagePreview =
                      Boolean(frame.imageUrl) && !isVideoMedia;
                    return (
                    <li key={`${frame.id}__${frameIdx}`} className="shot-subshot-frame-item">
                      <span className="meta-chip">
                        {t("storyboard.subShot.frameItem", { index: frameIdx + 1 })}
                      </span>
                      <span className="muted tabular-nums shot-subshot-frame-item__timing">
                        {imageTimingText(frame)}
                      </span>
                      {canShowImagePreview ? (
                        <AssetImagePreview
                          url={frame.imageUrl || ""}
                          name={
                            frame.frameName ||
                            frame.mediaName ||
                            visual.description ||
                            t("storyboard.frameFallback")
                          }
                          size="card"
                          projectId={projectId}
                          scriptId={scriptId}
                        />
                      ) : isVideoMedia ? (
                        <p className="muted">{t("storyboard.subShot.videoMisplacedInFrame")}</p>
                      ) : (
                        <p className="muted">{t("storyboard.subShot.framePendingOrUnavailable")}</p>
                      )}
                      {frame.frameAssetId ? (
                        <dl className="shot-segment-card__meta shot-visual-card__frame-asset">
                          <div>
                            <dt>{t("storyboard.subShot.asset")}</dt>
                            <dd>
                              {onNavigateAsset ? (
                                <button
                                  type="button"
                                  className="lineage-link-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onNavigateAsset(frame.frameAssetId!, "frame");
                                  }}
                                >
                                  {frame.frameAssetId}
                                </button>
                              ) : (
                                <code>{frame.frameAssetId}</code>
                              )}
                            </dd>
                          </div>
                        </dl>
                      ) : frame.imageMediaId && !isVideoMedia ? (
                        <dl className="shot-segment-card__meta shot-visual-card__frame-asset">
                          <div>
                            <dt>{t("storyboard.subShot.imageMediaAsset")}</dt>
                            <dd>
                              {onNavigateAsset ? (
                                <button
                                  type="button"
                                  className="lineage-link-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onNavigateAsset(frame.imageMediaId!, "media");
                                  }}
                                >
                                  {frame.mediaName || frame.imageMediaId}
                                </button>
                              ) : (
                                <code>{frame.mediaName || frame.imageMediaId}</code>
                              )}
                            </dd>
                          </div>
                        </dl>
                      ) : null}
                      {showFrameRegen && frame.frameAssetId ? (
                        <div
                          className="shot-subshot-content__regen"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <AssetRegenerateButton
                            projectId={projectId}
                            scriptId={scriptId}
                            assetId={frame.frameAssetId}
                            kind="frame"
                            layout="compact"
                            onDone={onRegenerateDone}
                          />
                        </div>
                      ) : null}
                    </li>
                    );
                  })}
                </ul>
              ) : null}
              {showFrameRegen && !showFrameSection ? (
                <div
                  className="shot-subshot-content__regen"
                  onClick={(e) => e.stopPropagation()}
                >
                  <AssetRegenerateButton
                    projectId={projectId}
                    scriptId={scriptId}
                    shotId={shotId}
                    shotKinds={["frame"]}
                    kind="frame"
                    layout="compact"
                    onDone={onRegenerateDone}
                  />
                </div>
              ) : null}
            </section>
          ) : null}

          {(showVideoSection || showVideoRegen) ? (
            <section className="shot-subshot-content shot-subshot-content--video">
              <span className="shot-subshot-content__eyebrow">
                {t("storyboard.subShot.videoSection")}
              </span>
              {showVideoSection ? (
                <ul className="shot-subshot-video-list">
                  {visual.videos
                    .filter((v) => v.mediaId || v.url || v.videoClipAssetId)
                    .map((vid, vidIdx) => (
                      <li key={vid.id} className="shot-subshot-video-item">
                        <span className="meta-chip">
                          {t("storyboard.subShot.videoItem", { index: vidIdx + 1 })}
                        </span>
                        {(vid.url ?? "").trim() ? (
                          <MediaPreview
                            kind="video"
                            url={vid.url!}
                            label={t("storyboard.subShot.videoPreview")}
                            projectId={projectId}
                            scriptId={scriptId}
                          />
                        ) : null}
                        {vid.videoClipAssetId || vid.mediaId ? (
                          <code>{vid.videoClipAssetId || vid.mediaId}</code>
                        ) : null}
                      </li>
                    ))}
                </ul>
              ) : null}
              {showVideoRegen ? (
                <div
                  className="shot-subshot-content__regen"
                  onClick={(e) => e.stopPropagation()}
                >
                  <AssetRegenerateButton
                    projectId={projectId}
                    scriptId={scriptId}
                    shotId={shotId}
                    shotKinds={["video"]}
                    kind="video"
                    layout="compact"
                    onDone={onRegenerateDone}
                  />
                </div>
              ) : null}
            </section>
          ) : null}

          {showTimeline && visual.timelineClip ? (
            <section className="shot-subshot-content shot-subshot-content--timeline">
              <span className="shot-subshot-content__eyebrow">
                {t("storyboard.subShot.timelineSection")}
              </span>
              <p className="muted tabular-nums">
                {formatMs(visual.timelineClip.startMs)}–{formatMs(visual.timelineClip.endMs)}
              </p>
              {visual.timelineClip.url ? (
                <MediaPreview
                  kind="video"
                  url={visual.timelineClip.url}
                  label={t("storyboard.subShot.timelinePreview")}
                  projectId={projectId}
                  scriptId={scriptId}
                />
              ) : null}
              {onOpenEditTimeline ? (
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenEditTimeline();
                  }}
                >
                  {t("storyboard.subShot.openEditTimeline")}
                </button>
              ) : null}
            </section>
          ) : null}

          {!showFrameSection &&
          !showFrameRegen &&
          !showVideoSection &&
          !showVideoRegen &&
          !showTimeline &&
          !showDescription ? (
            <p className="muted">{t("storyboard.subShot.noContent")}</p>
          ) : null}
        </>
      )}
    </article>
  );
}
