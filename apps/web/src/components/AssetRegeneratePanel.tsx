/**
 * 分镜详情二次生成面板：TTS / 画面 / 视频三卡片网格。
 */

import { useState } from "react";
import { AssetRegenerateButton, type RegenerateKind } from "./AssetRegenerateButton";
import { ShotVideoGenSourcePicker } from "./board/ShotVideoGenSourcePicker";
import { useAppTranslation } from "../i18n/useAppTranslation";
import { emptyVideoGenSource, type VideoGenSourceSelection } from "../utils/videoGenSource";

interface AssetRegeneratePanelProps {
  projectId: string;
  scriptId: string;
  shotId: string;
  disabled?: boolean;
  onDone?: () => void;
}

type ShotRegenItem = {
  kind: RegenerateKind;
  shotKinds: Array<"tts" | "frame" | "video">;
  eyebrowKey: string;
  hintKey: string;
};

const SHOT_REGEN_ITEMS: ShotRegenItem[] = [
  {
    kind: "tts",
    shotKinds: ["tts"],
    eyebrowKey: "regenerate.eyebrow.tts",
    hintKey: "regenerate.hint.tts",
  },
  {
    kind: "frame",
    shotKinds: ["frame"],
    eyebrowKey: "regenerate.eyebrow.frame",
    hintKey: "regenerate.hint.frame",
  },
  {
    kind: "video",
    shotKinds: ["video"],
    eyebrowKey: "regenerate.eyebrow.video",
    hintKey: "regenerate.hint.video",
  },
];

/** 分镜抽屉内二次生成三列卡片布局。 */
export function AssetRegeneratePanel({
  projectId,
  scriptId,
  shotId,
  disabled = false,
  onDone,
}: AssetRegeneratePanelProps) {
  const { t } = useAppTranslation("common");
  const { t: tBoard } = useAppTranslation("board");
  const [videoGenSource, setVideoGenSource] = useState<VideoGenSourceSelection>(() =>
    emptyVideoGenSource(0),
  );

  return (
    <div className="asset-regenerate-grid" role="group" aria-label={t("regenerate.panelLabel")}>
      {SHOT_REGEN_ITEMS.map((item) => (
        <article key={item.kind} className="asset-regenerate-card">
          <p className="asset-regenerate-card__eyebrow">{t(item.eyebrowKey)}</p>
          <p className="asset-regenerate-card__hint">{t(item.hintKey)}</p>
          {item.kind === "video" ? (
            <div className="asset-regenerate-card__video-source">
              <p className="asset-regenerate-card__video-source-label muted">
                {tBoard("storyboard.videoGen.sourceLead")}
              </p>
              <ShotVideoGenSourcePicker
                projectId={projectId}
                scriptId={scriptId}
                value={videoGenSource}
                onChange={setVideoGenSource}
              />
            </div>
          ) : null}
          <AssetRegenerateButton
            projectId={projectId}
            scriptId={scriptId}
            shotId={shotId}
            shotKinds={item.shotKinds}
            kind={item.kind}
            layout="card"
            disabled={disabled}
            videoOptions={item.kind === "video" ? videoGenSource : undefined}
            onDone={onDone}
          />
        </article>
      ))}
    </div>
  );
}
