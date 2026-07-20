/**
 * 镜内句级字幕编辑列表。
 */

import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { ShotSubtitleView } from "../../utils/shotSegmentUtils";

interface SubtitleSegmentEditorProps {
  durationMs: number;
  subtitles: ShotSubtitleView[];
  onChange: (lines: ShotSubtitleView[]) => void;
}

/** 句级字幕分段编辑。 */
export function SubtitleSegmentEditor({
  durationMs,
  subtitles,
  onChange,
}: SubtitleSegmentEditorProps) {
  const { t } = useAppTranslation("board");

  const updateLine = (id: string, patch: Partial<ShotSubtitleView>) => {
    onChange(subtitles.map((line) => (line.id === id ? { ...line, ...patch } : line)));
  };

  if (subtitles.length === 0) {
    return <p className="muted">{t("storyboard.subtitle.empty")}</p>;
  }

  return (
    <div className="shot-segment-editor__list">
      {subtitles.map((line, idx) => (
        <div key={line.id} className="shot-subtitle-card">
          <div className="shot-subtitle-card__head">
            <span className="muted">#{idx + 1}</span>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => onChange(subtitles.filter((s) => s.id !== line.id))}
            >
              {t("storyboard.subtitle.remove")}
            </button>
          </div>
          <label className="shot-editor-field">
            <span>{t("storyboard.subtitle.text")}</span>
            <textarea
              rows={2}
              value={line.text}
              onChange={(e) => updateLine(line.id, { text: e.target.value })}
            />
          </label>
          <div className="shot-subtitle-card__times">
            <label className="shot-editor-field">
              <span>{t("storyboard.subtitle.character")}</span>
              <input
                type="text"
                value={line.character}
                placeholder={t("storyboard.subtitle.characterPlaceholder")}
                onChange={(e) => updateLine(line.id, { character: e.target.value })}
              />
            </label>
            <label className="shot-editor-field">
              <span>{t("storyboard.subtitle.color")}</span>
              <input
                type="text"
                value={line.color}
                placeholder={t("storyboard.subtitle.colorPlaceholder")}
                onChange={(e) => updateLine(line.id, { color: e.target.value })}
              />
            </label>
          </div>
          <div className="shot-subtitle-card__times">
            <label className="shot-editor-field">
              <span>{t("storyboard.voiceAct.startMs")}</span>
              <input
                type="number"
                min={0}
                max={durationMs}
                value={line.startMs}
                onChange={(e) => updateLine(line.id, { startMs: Number(e.target.value) || 0 })}
              />
            </label>
            <label className="shot-editor-field">
              <span>{t("storyboard.voiceAct.endMs")}</span>
              <input
                type="number"
                min={0}
                max={durationMs}
                value={line.endMs}
                onChange={(e) =>
                  updateLine(line.id, { endMs: Number(e.target.value) || durationMs })
                }
              />
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}
