/**
 * 子镜画面挂接：可关联多张 frame，各带时段；用图文卡片选择资产。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { AssetImagePreview } from "../AssetImagePreview";
import { AssetRegenerateButton } from "../AssetRegenerateButton";
import { ImageTextAssetEditor } from "../ImageTextAssetEditor";
import type { ImageTextAssetItem } from "../ImageTextAssetCard";
import { CreateTextAssetDialog } from "../manual/CreateTextAssetDialog";
import type { ShotSubShotFrameView } from "../../utils/shotSegmentUtils";
import { newSubShotFrame } from "../../utils/shotSegmentUtils";
import { fetchBoardTextAssetItem } from "../../utils/boardTextAsset";
import {
  fetchFrameBoardOptions,
  frameViewFromBoardOption,
  type FrameBoardOption,
} from "../../utils/shotFrameBoard";
import { AssetVisualSelect, type AssetVisualOption } from "./AssetVisualSelect";

interface CreatedTextAsset {
  id?: string;
  name?: string;
  primary_media_id?: string;
  preview?: string;
}

interface ShotSubShotFramePickerProps {
  projectId: string;
  scriptId: string;
  shotId: string;
  images: ShotSubShotFrameView[];
  /** 所属子镜相对镜起点的时段，用作画面时段缺省。 */
  subShotStartMs: number;
  /** 所属子镜相对镜起点的时段终点。 */
  subShotEndMs: number;
  /** 外部高亮的槽位 id（迷你轴点选）。 */
  highlightSlotId?: string | null;
  onImagesChange: (images: ShotSubShotFrameView[]) => void;
  onRegenerateDone?: () => void;
}

/** 子镜多画面挂接面板。 */
export function ShotSubShotFramePicker({
  projectId,
  scriptId,
  shotId: _shotId,
  images,
  subShotStartMs,
  subShotEndMs,
  highlightSlotId,
  onImagesChange,
  onRegenerateDone,
}: ShotSubShotFramePickerProps) {
  void _shotId;
  const { t } = useAppTranslation("board");
  const { t: tc } = useAppTranslation("common");
  const [options, setOptions] = useState<FrameBoardOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [pendingSlotId, setPendingSlotId] = useState<string | null>(null);
  const [editing, setEditing] = useState<ImageTextAssetItem | null>(null);
  const [editLoading, setEditLoading] = useState(false);

  /** 刷新剧本画面看板选项。 */
  const loadFrames = useCallback(async () => {
    setLoading(true);
    try {
      setOptions(await fetchFrameBoardOptions(projectId, scriptId));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    void loadFrames();
  }, [loadFrames]);

  const selectedIds = useMemo(
    () =>
      images
        .map((img) => (img.frameAssetId ?? "").trim())
        .filter(Boolean),
    [images],
  );

  const visualOptions: AssetVisualOption[] = useMemo(
    () =>
      options.map((o) => ({
        id: o.id,
        name: o.name,
        summary: o.description,
        previewUrl: o.previewUrl,
      })),
    [options],
  );

  /** 修补某一画面槽。 */
  const patchSlot = (slotId: string, patch: Partial<ShotSubShotFrameView>) => {
    onImagesChange(images.map((img) => (img.id === slotId ? { ...img, ...patch } : img)));
  };

  /** 将看板画面写入指定槽（或新建槽）。 */
  const bindOption = (opt: FrameBoardOption, slotId?: string) => {
    if (slotId) {
      const existing = images.find((img) => img.id === slotId);
      const base = frameViewFromBoardOption(opt, slotId);
      patchSlot(slotId, {
        ...base,
        startMs: existing?.startMs ?? subShotStartMs,
        endMs: existing?.endMs ?? subShotEndMs,
        kind: existing?.kind ?? "static",
        sourceMediaIds: existing?.sourceMediaIds ?? [],
      });
      return;
    }
    const slot = newSubShotFrame();
    onImagesChange([
      ...images,
      {
        ...frameViewFromBoardOption(opt, slot.id),
        startMs: subShotStartMs,
        endMs: subShotEndMs,
        kind: "static",
        sourceMediaIds: [],
      },
    ]);
  };

  /** 点选卡片：始终追加一条挂接（同一画面可多次关联）。 */
  const handleVisualAdd = (assetId: string) => {
    if (!assetId) return;
    const opt = options.find((o) => o.id === assetId);
    if (opt) bindOption(opt);
  };

  /** 胶片条按序移除对应槽位（含重复挂接的同画面）。 */
  const handleVisualDeselectAt = (index: number) => {
    const linked = images.filter((img) => (img.frameAssetId ?? "").trim());
    const target = linked[index];
    if (!target) return;
    onImagesChange(images.filter((img) => img.id !== target.id));
  };

  /** 新建画面后挂到指定槽或新增槽。 */
  const handleCreated = (asset?: CreatedTextAsset) => {
    void (async () => {
      const freshOptions = await fetchFrameBoardOptions(projectId, scriptId);
      setOptions(freshOptions);
      const assetId = (asset?.id ?? "").trim();
      if (!assetId) {
        setCreateOpen(false);
        setPendingSlotId(null);
        return;
      }
      const fromBoard = freshOptions.find((o) => o.id === assetId);
      const opt: FrameBoardOption =
        fromBoard ??
        ({
          id: assetId,
          name: String(asset?.name ?? assetId),
          description: "",
          previewUrl: String(asset?.preview ?? ""),
          primaryMediaId: String(asset?.primary_media_id ?? ""),
          elementRefs: {},
        } satisfies FrameBoardOption);
      bindOption(opt, pendingSlotId ?? undefined);
      setCreateOpen(false);
      setPendingSlotId(null);
    })();
  };

  /** 打开某画面的编辑弹窗。 */
  const openEdit = (frameAssetId: string) => {
    const assetId = frameAssetId.trim();
    if (!assetId) return;
    setEditLoading(true);
    void (async () => {
      try {
        const item = await fetchBoardTextAssetItem(projectId, scriptId, "frame", assetId);
        if (item) setEditing(item);
      } finally {
        setEditLoading(false);
      }
    })();
  };

  return (
    <section className="shot-frame-panel">
      <header className="shot-frame-panel__head">
        <div>
          <h4 className="shot-frame-panel__title">{t("storyboard.subShot.frameSection")}</h4>
          <p className="muted shot-frame-panel__lead">{t("storyboard.subShot.framePanelLead")}</p>
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
            {t("storyboard.subShot.frameCreateNew")}
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
        emptyLabel={t("storyboard.subShot.linkEmpty")}
        projectId={projectId}
        scriptId={scriptId}
        showSelectedStrip
      />

      {images.length > 0 ? (
        <ul className="shot-frame-panel__list">
          {images.map((img, idx) => {
            const opt = options.find((o) => o.id === img.frameAssetId);
            const highlighted = highlightSlotId === img.id;
            return (
              <li
                key={img.id}
                className={`shot-frame-slot${highlighted ? " is-highlighted" : ""}`}
                id={`subshot-frame-${img.id}`}
              >
                <div className="shot-frame-slot__hero">
                  <div className="shot-frame-slot__preview">
                    {img.mediaType === "video" ? (
                      <div className="shot-frame-slot__preview-placeholder">
                        <span>{t("storyboard.subShot.videoMisplacedInFrame")}</span>
                      </div>
                    ) : opt?.previewUrl || (img.imageUrl && img.mediaType !== "video") ? (
                      <AssetImagePreview
                        url={opt?.previewUrl || img.imageUrl || ""}
                        name={
                          opt?.name ||
                          img.frameName ||
                          img.mediaName ||
                          t("storyboard.frameFallback")
                        }
                        size="card"
                        projectId={projectId}
                        scriptId={scriptId}
                      />
                    ) : (
                      <div className="shot-frame-slot__preview-placeholder">
                        <span>
                          {img.imageMediaId
                            ? t("storyboard.subShot.framePendingOrUnavailable")
                            : t("storyboard.noFrameYet")}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="shot-frame-slot__main">
                    <div className="shot-frame-slot__head">
                      <span className="shot-frame-slot__index">
                        {t("storyboard.subShot.frameItem", { index: idx + 1 })}
                      </span>
                      <span className="meta-chip tabular-nums">
                        {img.frameAssetId ||
                          (img.imageMediaId && img.mediaType !== "video"
                            ? t("storyboard.subShot.imageBoundNoFrame")
                            : t("storyboard.subShot.frameSelectPlaceholder"))}
                      </span>
                    </div>
                    {img.mediaType === "video" ? (
                      <p className="muted shot-frame-slot__desc">
                        {t("storyboard.subShot.videoMisplacedInFrame")}
                      </p>
                    ) : (opt?.description || img.frameName || img.mediaName) ? (
                      <p className="muted shot-frame-slot__desc">
                        {opt?.description || img.frameName || img.mediaName}
                      </p>
                    ) : !img.frameAssetId && img.imageMediaId ? (
                      <p className="muted shot-frame-slot__desc">
                        {t("storyboard.subShot.imageBoundNoFrameHint")}
                      </p>
                    ) : null}
                    <div className="shot-frame-slot__timing">
                      <label className="shot-segment-field">
                        <span>{t("storyboard.subShot.imageStartMs")}</span>
                        <input
                          type="number"
                          min={subShotStartMs}
                          max={subShotEndMs}
                          value={img.startMs ?? subShotStartMs}
                          onChange={(e) =>
                            patchSlot(img.id, { startMs: Number(e.target.value) || 0 })
                          }
                        />
                      </label>
                      <label className="shot-segment-field">
                        <span>{t("storyboard.subShot.imageEndMs")}</span>
                        <input
                          type="number"
                          min={subShotStartMs}
                          max={subShotEndMs}
                          value={img.endMs ?? subShotEndMs}
                          onChange={(e) =>
                            patchSlot(img.id, { endMs: Number(e.target.value) || 0 })
                          }
                        />
                      </label>
                    </div>
                    <div className="shot-frame-slot__head-actions">
                      {img.frameAssetId ? (
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          disabled={editLoading}
                          onClick={() => openEdit(img.frameAssetId!)}
                        >
                          {editLoading ? t("storyboard.assetPicker.loading") : tc("actions.edit")}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() => {
                          setPendingSlotId(img.id);
                          setCreateOpen(true);
                        }}
                      >
                        {t("storyboard.subShot.frameCreateNew")}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() =>
                          onImagesChange(images.filter((row) => row.id !== img.id))
                        }
                      >
                        {t("storyboard.subShot.frameRemove")}
                      </button>
                    </div>
                  </div>
                </div>
                {img.frameAssetId ? (
                  <div className="shot-frame-slot__regen">
                    <AssetRegenerateButton
                      projectId={projectId}
                      scriptId={scriptId}
                      assetId={img.frameAssetId}
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

      {createOpen ? (
        <CreateTextAssetDialog
          projectId={projectId}
          scriptId={scriptId}
          assetType="frame"
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
            void loadFrames();
            onRegenerateDone?.();
          }}
        />
      ) : null}
    </section>
  );
}
