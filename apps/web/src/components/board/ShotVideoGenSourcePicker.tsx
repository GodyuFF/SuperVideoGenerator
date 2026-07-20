/**
 * AI 视频生成参考源多选（非分镜挂接）：画面、落盘图片、角色/场景/道具形象。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { type ElementRefBucket } from "../../utils/elementRefUtils";
import { fetchFrameBoardOptions, type FrameBoardOption } from "../../utils/shotFrameBoard";
import {
  fetchVideoClipBoardOptions,
  type VideoClipBoardOption,
} from "../../utils/shotVideoClipBoard";
import type { ShotSubShotFrameView } from "../../utils/shotSegmentUtils";
import {
  countVideoGenSources,
  emptyVideoGenSource,
  type VideoGenSourceSelection,
} from "../../utils/videoGenSource";

const API = "/api";

interface MediaListItem {
  id?: string;
  name?: string;
  type?: string;
}

interface AssetOption {
  id: string;
  name: string;
}

interface ShotVideoGenSourcePickerProps {
  projectId: string;
  scriptId: string;
  subShotIdx?: number;
  /** 子镜已关联画面，作为默认可选项。 */
  subShotFrames?: ShotSubShotFrameView[];
  value?: VideoGenSourceSelection;
  onChange: (next: VideoGenSourceSelection) => void;
  className?: string;
}

const REF_BUCKETS: ElementRefBucket[] = ["character", "scene", "prop"];

/** 视频生成参考源多选面板。 */
export function ShotVideoGenSourcePicker({
  projectId,
  scriptId,
  subShotIdx = 0,
  subShotFrames = [],
  value,
  onChange,
  className = "shot-video-gen-source",
}: ShotVideoGenSourcePickerProps) {
  const { t } = useAppTranslation("board");
  const selection = value ?? emptyVideoGenSource(subShotIdx);
  const [frameOptions, setFrameOptions] = useState<FrameBoardOption[]>([]);
  const [clipOptions, setClipOptions] = useState<VideoClipBoardOption[]>([]);
  const [imageOptions, setImageOptions] = useState<AssetOption[]>([]);
  const [elementOptions, setElementOptions] = useState<Record<ElementRefBucket, AssetOption[]>>({
    character: [],
    scene: [],
    prop: [],
    frame: [],
  });
  const [loading, setLoading] = useState(false);

  const mergedFrameOptions = useMemo(() => {
    const map = new Map<string, { id: string; name: string }>();
    for (const f of subShotFrames) {
      const id = (f.frameAssetId ?? "").trim();
      if (!id) continue;
      map.set(id, { id, name: f.frameName || id });
    }
    for (const opt of frameOptions) {
      if (!map.has(opt.id)) {
        map.set(opt.id, { id: opt.id, name: opt.name });
      }
    }
    return [...map.values()];
  }, [frameOptions, subShotFrames]);

  /** 拉取画面、图片与元素看板选项。 */
  const loadOptions = useCallback(async () => {
    setLoading(true);
    try {
      setFrameOptions(await fetchFrameBoardOptions(projectId, scriptId));
      setClipOptions(await fetchVideoClipBoardOptions(projectId, scriptId));

      const mediaRes = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/media`);
      if (mediaRes.ok) {
        const items = (await mediaRes.json()) as MediaListItem[];
        setImageOptions(
          items
            .filter((m) => m.type === "image")
            .map((m) => ({
              id: String(m.id ?? "").trim(),
              name: String(m.name ?? m.id ?? ""),
            }))
            .filter((m) => m.id),
        );
      } else {
        setImageOptions([]);
      }

      const nextElements: Record<ElementRefBucket, AssetOption[]> = {
        character: [],
        scene: [],
        prop: [],
        frame: [],
      };
      await Promise.all(
        REF_BUCKETS.map(async (kind) => {
          const params = new URLSearchParams({ script_id: scriptId });
          const res = await fetch(`${API}/projects/${projectId}/board/${kind}?${params}`);
          if (!res.ok) return;
          const data = (await res.json()) as { items?: Record<string, unknown>[] };
          nextElements[kind] = (data.items ?? [])
            .map((item) => ({
              id: String(item.id ?? item.asset_id ?? ""),
              name: String(item.name ?? item.id ?? ""),
            }))
            .filter((o) => o.id);
        }),
      );
      setElementOptions(nextElements);
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  /** 切换 video_clip 参考勾选。 */
  const toggleVideoClip = (id: string) => {
    const set = new Set(selection.sourceVideoClipAssetIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange({ ...selection, subShotIdx, sourceVideoClipAssetIds: [...set] });
  };

  /** 切换画面参考勾选。 */
  const toggleFrame = (id: string) => {
    const set = new Set(selection.sourceFrameAssetIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange({ ...selection, subShotIdx, sourceFrameAssetIds: [...set] });
  };

  /** 切换落盘图片参考勾选。 */
  const toggleMedia = (id: string) => {
    const set = new Set(selection.sourceMediaIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange({ ...selection, subShotIdx, sourceMediaIds: [...set] });
  };

  /** 切换元素（角色/场景/道具）参考勾选。 */
  const toggleElement = (bucket: ElementRefBucket, id: string) => {
    const prev = selection.sourceElementRefs[bucket] ?? [];
    const set = new Set(prev);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    const nextRefs = { ...selection.sourceElementRefs, [bucket]: [...set] };
    if (!nextRefs[bucket]?.length) delete nextRefs[bucket];
    onChange({ ...selection, subShotIdx, sourceElementRefs: nextRefs });
  };

  const sourceCount = countVideoGenSources(selection);
  const inferredMode =
    sourceCount >= 2 ? "keyframes" : sourceCount === 1 ? "img2video" : null;

  return (
    <div className={className}>
      <p className="shot-video-gen-source__lead muted">
        {t("storyboard.videoGen.sourceLead")}
      </p>
      {loading ? <p className="muted">{t("storyboard.assetPicker.loading")}</p> : null}

      {clipOptions.length > 0 ? (
        <fieldset className="shot-video-gen-source__group">
          <legend>{t("storyboard.videoGen.sourceVideoClips")}</legend>
          <ul className="shot-video-gen-source__list">
            {clipOptions.map((c) => (
              <li key={c.id}>
                <label className="shot-video-gen-source__check">
                  <input
                    type="checkbox"
                    checked={selection.sourceVideoClipAssetIds.includes(c.id)}
                    onChange={() => toggleVideoClip(c.id)}
                  />
                  <span>{c.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ) : null}

      {mergedFrameOptions.length > 0 ? (
        <fieldset className="shot-video-gen-source__group">
          <legend>{t("storyboard.videoGen.sourceFrames")}</legend>
          <ul className="shot-video-gen-source__list">
            {mergedFrameOptions.map((f) => (
              <li key={f.id}>
                <label className="shot-video-gen-source__check">
                  <input
                    type="checkbox"
                    checked={selection.sourceFrameAssetIds.includes(f.id)}
                    onChange={() => toggleFrame(f.id)}
                  />
                  <span>{f.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ) : null}

      {imageOptions.length > 0 ? (
        <fieldset className="shot-video-gen-source__group">
          <legend>{t("storyboard.videoGen.sourceImages")}</legend>
          <ul className="shot-video-gen-source__list">
            {imageOptions.map((img) => (
              <li key={img.id}>
                <label className="shot-video-gen-source__check">
                  <input
                    type="checkbox"
                    checked={selection.sourceMediaIds.includes(img.id)}
                    onChange={() => toggleMedia(img.id)}
                  />
                  <span>{img.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ) : null}

      {REF_BUCKETS.map((bucket) =>
        elementOptions[bucket].length > 0 ? (
          <fieldset key={bucket} className="shot-video-gen-source__group">
            <legend>{t(`storyboard.videoGen.sourceBucket.${bucket}`)}</legend>
            <ul className="shot-video-gen-source__list">
              {elementOptions[bucket].map((opt) => (
                <li key={opt.id}>
                  <label className="shot-video-gen-source__check">
                    <input
                      type="checkbox"
                      checked={(selection.sourceElementRefs[bucket] ?? []).includes(opt.id)}
                      onChange={() => toggleElement(bucket, opt.id)}
                    />
                    <span>{opt.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        ) : null,
      )}

      {sourceCount > 0 ? (
        <p className="shot-video-gen-source__summary muted">
          {t("storyboard.videoGen.sourceSummary", {
            count: sourceCount,
            mode: inferredMode
              ? t(`storyboard.subShot.genMode.${inferredMode}`)
              : t("storyboard.videoGen.modeAuto"),
          })}
        </p>
      ) : (
        <p className="muted">{t("storyboard.videoGen.sourceEmpty")}</p>
      )}
    </div>
  );
}
