/**
 * 子镜视频挂接：可关联多段 video_clip，各带时段；用图文卡片选择资产。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { AssetRegenerateButton } from "../AssetRegenerateButton";
import { ImageTextAssetEditor } from "../ImageTextAssetEditor";
import type { ImageTextAssetItem } from "../ImageTextAssetCard";
import { MediaPreview } from "../MediaPreview";
import { CreateTextAssetDialog } from "../manual/CreateTextAssetDialog";
import type { ShotSubShotVideoView } from "../../utils/shotSegmentUtils";
import { newSubShotVideo } from "../../utils/shotSegmentUtils";
import { looksLikeMediaUrl } from "../../utils/boardMediaPreview";
import { fetchBoardTextAssetItem } from "../../utils/boardTextAsset";
import {
  fetchVideoClipBoardOptions,
  videoClipViewFromBoardOption,
  type VideoClipBoardOption,
} from "../../utils/shotVideoClipBoard";
import { AssetVisualSelect, type AssetVisualOption } from "./AssetVisualSelect";

interface CreatedTextAsset {
  id?: string;
  name?: string;
  primary_media_id?: string;
  preview?: string;
}

interface ShotSubShotVideoPickerProps {
  projectId: string;
  scriptId: string;
  shotId: string;
  /** 子镜索引，写入 regenerate API 的 video.sub_shot_idx。 */
  subShotIdx?: number;
  videos: ShotSubShotVideoView[];
  subShotStartMs: number;
  subShotEndMs: number;
  /** 外部高亮的槽位 id（迷你轴点选）。 */
  highlightSlotId?: string | null;
  onChange: (videos: ShotSubShotVideoView[]) => void;
  onRegenerateDone?: () => void;
}

/** 子镜多视频挂接面板。 */
export function ShotSubShotVideoPicker({
  projectId,
  scriptId,
  shotId,
  subShotIdx = 0,
  videos,
  subShotStartMs,
  subShotEndMs,
  highlightSlotId,
  onChange,
  onRegenerateDone,
}: ShotSubShotVideoPickerProps) {
  const { t } = useAppTranslation("board");
  const { t: tc } = useAppTranslation("common");
  const [clipOptions, setClipOptions] = useState<VideoClipBoardOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingSlotId, setPendingSlotId] = useState<string | null>(null);
  const [editing, setEditing] = useState<ImageTextAssetItem | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  /** 刷新剧本 video_clip 看板选项。 */
  const loadClips = useCallback(async () => {
    setLoading(true);
    try {
      setClipOptions(await fetchVideoClipBoardOptions(projectId, scriptId));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    void loadClips();
  }, [loadClips]);

  const selectedIds = useMemo(
    () =>
      videos
        .map((v) => (v.videoClipAssetId ?? "").trim())
        .filter(Boolean),
    [videos],
  );

  const visualOptions: AssetVisualOption[] = useMemo(
    () =>
      clipOptions.map((o) => ({
        id: o.id,
        name: o.name,
        summary: o.summary,
        previewUrl: o.previewUrl,
      })),
    [clipOptions],
  );

  /** 修补某一视频槽。 */
  const patchSlot = (slotId: string, patch: Partial<ShotSubShotVideoView>) => {
    onChange(videos.map((v) => (v.id === slotId ? { ...v, ...patch } : v)));
  };

  /** 将看板 video_clip 写入指定槽或新建槽。 */
  const bindOption = (opt: VideoClipBoardOption, slotId?: string) => {
    if (slotId) {
      const existing = videos.find((v) => v.id === slotId);
      const next = videoClipViewFromBoardOption(
        opt,
        slotId,
        existing?.startMs ?? subShotStartMs,
        existing?.endMs ?? subShotEndMs,
      );
      patchSlot(slotId, next);
      return;
    }
    const slot = newSubShotVideo(subShotStartMs, subShotEndMs);
    onChange([
      ...videos,
      videoClipViewFromBoardOption(opt, slot.id, subShotStartMs, subShotEndMs),
    ]);
  };

  /** 点选卡片：始终追加一条挂接（同一视频片段可多次关联）。 */
  const handleVisualAdd = (assetId: string) => {
    if (!assetId) return;
    const opt = clipOptions.find((o) => o.id === assetId);
    if (opt) bindOption(opt);
  };

  /** 胶片条按序移除对应槽位（含重复挂接）。 */
  const handleVisualDeselectAt = (index: number) => {
    const linked = videos.filter((v) => (v.videoClipAssetId ?? "").trim());
    const target = linked[index];
    if (!target) return;
    onChange(videos.filter((v) => v.id !== target.id));
  };

  /** 新建视频片段后挂接。 */
  const handleCreated = (asset?: CreatedTextAsset) => {
    void (async () => {
      const fresh = await fetchVideoClipBoardOptions(projectId, scriptId);
      setClipOptions(fresh);
      const assetId = (asset?.id ?? "").trim();
      if (!assetId) {
        setCreateOpen(false);
        setPendingSlotId(null);
        return;
      }
      const fromBoard = fresh.find((o) => o.id === assetId);
      const rawPreview = String(asset?.preview ?? "").trim();
      const opt: VideoClipBoardOption =
        fromBoard ??
        ({
          id: assetId,
          name: String(asset?.name ?? assetId),
          summary: "",
          previewUrl: looksLikeMediaUrl(rawPreview) ? rawPreview : undefined,
          primaryMediaId: String(asset?.primary_media_id ?? ""),
          elementRefs: {},
        } satisfies VideoClipBoardOption);
      bindOption(opt, pendingSlotId ?? undefined);
      setCreateOpen(false);
      setPendingSlotId(null);
    })();
  };

  /** 打开编辑弹窗。 */
  const openEdit = (videoClipAssetId: string) => {
    const assetId = videoClipAssetId.trim();
    if (!assetId) return;
    setEditLoading(true);
    void (async () => {
      try {
        const item = await fetchBoardTextAssetItem(
          projectId,
          scriptId,
          "video_clip",
          assetId,
        );
        if (item) setEditing(item);
      } finally {
        setEditLoading(false);
      }
    })();
  };

  return (
    <section className="shot-subshot-content shot-subshot-content--video">
      <header className="shot-frame-panel__head">
        <div>
          <h4 className="shot-frame-panel__title">{t("storyboard.subShot.videoSection")}</h4>
          <p className="muted shot-frame-panel__lead">{t("storyboard.subShot.videoPanelLead")}</p>
        </div>
        <div className="shot-subshot-frame-picker__actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => {
              setPendingSlotId(null);
              setCreateOpen(true);
            }}
          >
            {t("storyboard.subShot.videoCreateNew")}
          </button>
        </div>
      </header>

      <AssetVisualSelect
        options={visualOptions}
        selectedIds={selectedIds}
        onToggle={handleVisualAdd}
        onDeselectAt={handleVisualDeselectAt}
        mode="multi"
        allowDuplicateSelection
        loading={loading}
        emptyLabel={t("storyboard.subShot.videoEmpty")}
        projectId={projectId}
        scriptId={scriptId}
        showSelectedStrip
        hideEmptyPreview
      />

      {videos.length > 0 ? (
        <ul className="shot-frame-panel__list">
          {videos.map((vid, idx) => {
            const opt = clipOptions.find((o) => o.id === vid.videoClipAssetId);
            const highlighted = highlightSlotId === vid.id;
            const previewUrl = (vid.url || opt?.previewUrl || "").trim();
            return (
              <li
                key={vid.id}
                className={`shot-frame-slot${highlighted ? " is-highlighted" : ""}`}
                id={`subshot-video-${vid.id}`}
              >
                <div className="shot-frame-slot__hero">
                  {previewUrl ? (
                    <div className="shot-frame-slot__preview">
                      <MediaPreview
                        kind="video"
                        url={previewUrl}
                        label={opt?.name || vid.videoClipName || t("storyboard.subShot.videoPreview")}
                        projectId={projectId}
                        scriptId={scriptId}
                      />
                    </div>
                  ) : null}
                  <div className="shot-frame-slot__main">
                    <div className="shot-frame-slot__head">
                      <span className="shot-frame-slot__index">
                        {t("storyboard.subShot.videoItem", { index: idx + 1 })}
                      </span>
                      <span className="meta-chip tabular-nums">
                        {vid.videoClipAssetId ||
                          t("storyboard.subShot.videoSourceClipPlaceholder")}
                      </span>
                    </div>
                    {(opt?.summary || vid.videoClipName) ? (
                      <p className="muted shot-frame-slot__desc">
                        {opt?.summary || vid.videoClipName}
                      </p>
                    ) : null}
                    <div className="shot-frame-slot__timing">
                      <label className="shot-segment-field">
                        <span>{t("storyboard.subShot.videoStartMs")}</span>
                        <input
                          type="number"
                          min={subShotStartMs}
                          max={subShotEndMs}
                          value={vid.startMs}
                          onChange={(e) =>
                            patchSlot(vid.id, { startMs: Number(e.target.value) || 0 })
                          }
                        />
                      </label>
                      <label className="shot-segment-field">
                        <span>{t("storyboard.subShot.videoEndMs")}</span>
                        <input
                          type="number"
                          min={subShotStartMs}
                          max={subShotEndMs}
                          value={vid.endMs}
                          onChange={(e) =>
                            patchSlot(vid.id, { endMs: Number(e.target.value) || 0 })
                          }
                        />
                      </label>
                    </div>
                    <div className="shot-frame-slot__head-actions">
                      {vid.videoClipAssetId ? (
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          disabled={editLoading}
                          onClick={() => openEdit(vid.videoClipAssetId!)}
                        >
                          {editLoading ? t("storyboard.assetPicker.loading") : tc("actions.edit")}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() => {
                          setPendingSlotId(vid.id);
                          setCreateOpen(true);
                        }}
                      >
                        {t("storyboard.subShot.videoCreateNew")}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() => onChange(videos.filter((row) => row.id !== vid.id))}
                      >
                        {t("storyboard.subShot.videoRemove")}
                      </button>
                    </div>
                  </div>
                </div>
                {vid.videoClipAssetId ? (
                  <div className="shot-frame-slot__regen">
                    <AssetRegenerateButton
                      projectId={projectId}
                      scriptId={scriptId}
                      assetId={vid.videoClipAssetId}
                      shotId={shotId}
                      shotKinds={["video"]}
                      kind="video"
                      layout="compact"
                      videoOptions={{
                        subShotIdx,
                        sourceFrameAssetIds: [],
                      }}
                      onDone={onRegenerateDone}
                    />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {createOpen ? (
        <CreateTextAssetDialog
          projectId={projectId}
          scriptId={scriptId}
          assetType="video_clip"
          onClose={() => {
            setCreateOpen(false);
            setPendingSlotId(null);
          }}
          onCreated={handleCreated}
        />
      ) : null}

      {editing ? (
        <ImageTextAssetEditor
          projectId={projectId}
          scriptId={scriptId}
          item={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void loadClips();
            onRegenerateDone?.();
          }}
        />
      ) : null}
    </section>
  );
}
