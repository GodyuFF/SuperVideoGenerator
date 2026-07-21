/**
 * AI 视频生成参考源多选（非分镜挂接）：仅剧本画面。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { fetchFrameBoardOptions, type FrameBoardOption } from "../../utils/shotFrameBoard";
import type { ShotSubShotFrameView } from "../../utils/shotSegmentUtils";
import {
  countVideoGenSources,
  emptyVideoGenSource,
  type VideoGenSourceSelection,
} from "../../utils/videoGenSource";

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

/** 视频生成参考源多选面板（仅画面）。 */
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

  /** 拉取剧本画面看板选项。 */
  const loadOptions = useCallback(async () => {
    setLoading(true);
    try {
      setFrameOptions(await fetchFrameBoardOptions(projectId, scriptId));
    } finally {
      setLoading(false);
    }
  }, [projectId, scriptId]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  /** 切换画面参考勾选。 */
  const toggleFrame = (id: string) => {
    const set = new Set(selection.sourceFrameAssetIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange({ ...selection, subShotIdx, sourceFrameAssetIds: [...set] });
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
