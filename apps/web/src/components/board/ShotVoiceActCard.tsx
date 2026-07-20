/**
 * 单条配音幕卡片：时间码、角色语音（character_ref→TTS）、音频上传与试听/重生。
 * 角色仅表示发言人音色，不是分镜子镜挂接槽。
 */

import { useRef, useState } from "react";
import { AssetRegenerateButton } from "../AssetRegenerateButton";
import { MediaPreview } from "../MediaPreview";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import { previewTtsVoice, useTtsVoices } from "../../hooks/useTtsVoices";
import { uploadShotVoiceAudio } from "../../lib/voiceAudioUpload";
import { formatMs } from "./storyboardShared";
import type { ShotVoiceActView } from "../../utils/shotSegmentUtils";
import {
  resolveCharacterDisplayName,
  voiceActPatchForCharacter,
  type CharacterBoardOption,
} from "../../utils/shotCharacterBoard";

interface ShotVoiceActCardProps {
  act: ShotVoiceActView;
  index: number;
  projectId: string;
  scriptId: string;
  shotId: string;
  selected?: boolean;
  editable?: boolean;
  regenerateEnabled?: boolean;
  characterOptions?: CharacterBoardOption[];
  charactersLoading?: boolean;
  onSelect?: () => void;
  onChange?: (patch: Partial<ShotVoiceActView>) => void;
  onRemove?: () => void;
  onRegenerateDone?: () => void;
  /** 上传或服务端绑定音频后刷新计划稿。 */
  onAudioSynced?: () => void;
}

/** 配音幕只读/编辑卡片。 */
export function ShotVoiceActCard({
  act,
  index,
  projectId,
  scriptId,
  shotId,
  selected,
  editable,
  regenerateEnabled,
  characterOptions = [],
  charactersLoading,
  onSelect,
  onChange,
  onRemove,
  onRegenerateDone,
  onAudioSynced,
}: ShotVoiceActCardProps) {
  const { t } = useAppTranslation("board");
  const { voices, config, loading: voicesLoading } = useTtsVoices(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const narratorLabel = t("storyboard.voiceAct.narratorFallback");
  const characterLabel = resolveCharacterDisplayName(
    act.characterRef,
    characterOptions,
    narratorLabel,
  );
  const linkedCharacter = characterOptions.find((o) => o.id === act.characterRef.trim());
  const voiceFromCharacter = Boolean(linkedCharacter?.ttsVoice && act.voice === linkedCharacter.ttsVoice);
  const effectiveVoice = act.voice || config?.defaultVoice || "";

  const handleCharacterChange = (nextRef: string) => {
    if (!onChange) return;
    onChange(voiceActPatchForCharacter(nextRef, characterOptions));
  };

  /** 试听当前选中 TTS 音色。 */
  const handleVoicePreview = async () => {
    if (!effectiveVoice) return;
    setPreviewing(true);
    try {
      const url = await previewTtsVoice(act.text, effectiveVoice, config?.provider);
      if (url) setPreviewUrl(url);
    } finally {
      setPreviewing(false);
    }
  };

  /** 上传本地音频并绑定到本条配音幕。 */
  const handleAudioUpload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadShotVoiceAudio(projectId, scriptId, shotId, file, {
        clipId: act.id.startsWith("vac-") ? undefined : act.id,
        narrationText: act.text,
        bindClip: true,
      });
      onChange?.({
        mediaId: result.media_id,
        audioUrl: result.link,
        endMs: result.duration_ms ? act.startMs + result.duration_ms : act.endMs,
      });
      onAudioSynced?.();
    } catch (err) {
      setUploadError((err as Error).message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <article
      className={`shot-segment-card shot-voice-act-card${selected ? " is-selected" : ""}`}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (!onSelect) return;
        const tag = (e.target as HTMLElement).tagName;
        if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
    >
      <header className="shot-segment-card__head">
        <span className="shot-segment-card__eyebrow">
          {t("storyboard.voiceAct.title", { index: index + 1 })}
        </span>
        <span className="shot-segment-card__time tabular-nums">
          {formatMs(act.startMs)}–{formatMs(act.endMs)}
        </span>
        {editable && onRemove ? (
          <button
            type="button"
            className="btn-secondary btn-sm shot-segment-card__remove"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
          >
            {t("storyboard.voiceAct.remove")}
          </button>
        ) : null}
      </header>

      {editable && onChange ? (
        <div
          className="shot-segment-card__fields"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <label className="shot-segment-field">
            <span>{t("storyboard.voiceAct.startMs")}</span>
            <input
              type="number"
              min={0}
              value={act.startMs}
              onChange={(e) => onChange({ startMs: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="shot-segment-field">
            <span>{t("storyboard.voiceAct.endMs")}</span>
            <input
              type="number"
              min={0}
              value={act.endMs}
              onChange={(e) => onChange({ endMs: Number(e.target.value) || 0 })}
            />
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.voiceAct.character")}</span>
            <select
              value={act.characterRef}
              disabled={charactersLoading}
              title={t("storyboard.voiceAct.characterHint")}
              onChange={(e) => handleCharacterChange(e.target.value)}
            >
              <option value="">{narratorLabel}</option>
              {characterOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.ttsVoice ? ` · ${t("storyboard.voiceAct.hasVoice")}` : ""}
                </option>
              ))}
            </select>
            <span className="muted shot-segment-field__hint">{t("storyboard.voiceAct.characterHint")}</span>
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.voiceAct.voice")}</span>
            <div className="shot-voice-act-voice-row">
              <select
                value={act.voice}
                disabled={voicesLoading}
                onChange={(e) => onChange({ voice: e.target.value })}
              >
                <option value="">
                  {config?.defaultVoice
                    ? t("storyboard.voiceAct.voiceDefault", { voice: config.defaultVoice })
                    : t("storyboard.voiceAct.voicePlaceholder")}
                </option>
                {voices.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={!effectiveVoice || previewing}
                onClick={() => void handleVoicePreview()}
              >
                {previewing ? t("storyboard.voiceAct.previewing") : t("storyboard.voiceAct.previewVoice")}
              </button>
            </div>
            {voiceFromCharacter ? (
              <span className="muted shot-voice-act-voice-hint">
                {t("storyboard.voiceAct.voiceFromCharacter", { name: linkedCharacter?.name ?? "" })}
              </span>
            ) : null}
          </label>
          <label className="shot-segment-field shot-segment-field--full">
            <span>{t("storyboard.voiceAct.text")}</span>
            <textarea
              rows={3}
              value={act.text}
              onChange={(e) => onChange({ text: e.target.value })}
            />
          </label>
          <div className="shot-segment-field shot-segment-field--full shot-voice-act-audio-block">
            <span>{t("storyboard.voiceAct.audioSource")}</span>
            <div className="shot-voice-act-audio-actions">
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*,.mp3,.wav,.m4a,.ogg,.webm,.aac,.flac"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleAudioUpload(file);
                }}
              />
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? t("storyboard.voiceAct.uploading") : t("storyboard.voiceAct.uploadAudio")}
              </button>
              {act.mediaId ? (
                <span className="muted shot-voice-act-audio-bound">
                  {t("storyboard.voiceAct.audioBound")}
                </span>
              ) : (
                <span className="muted">{t("storyboard.voiceAct.audioOrTtsHint")}</span>
              )}
            </div>
            {uploadError ? (
              <p className="board-error shot-voice-act-upload-error" role="alert">
                {uploadError}
              </p>
            ) : null}
            {act.audioUrl ? (
              <div
                className="shot-voice-act-audio-preview"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <MediaPreview
                  kind="audio"
                  url={act.audioUrl}
                  projectId={projectId}
                  scriptId={scriptId}
                  label={t("storyboard.previewTts")}
                  className="shot-tts-preview"
                />
              </div>
            ) : null}
            {previewUrl ? (
              <div
                className="shot-voice-act-audio-preview"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <MediaPreview
                  kind="audio"
                  url={previewUrl}
                  label={t("storyboard.voiceAct.previewVoice")}
                  className="shot-tts-preview"
                />
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <>
          <dl className="shot-segment-card__meta">
            <div>
              <dt>{t("storyboard.voiceAct.character")}</dt>
              <dd>{characterLabel}</dd>
            </div>
            {act.voice ? (
              <div>
                <dt>{t("storyboard.voiceAct.voice")}</dt>
                <dd>{act.voice}</dd>
              </div>
            ) : linkedCharacter?.ttsVoice ? (
              <div>
                <dt>{t("storyboard.voiceAct.voice")}</dt>
                <dd className="muted">{linkedCharacter.ttsVoice}</dd>
              </div>
            ) : config?.defaultVoice ? (
              <div>
                <dt>{t("storyboard.voiceAct.voice")}</dt>
                <dd className="muted">{config.defaultVoice}</dd>
              </div>
            ) : null}
          </dl>
          {act.text ? <p className="shot-segment-card__body">{act.text}</p> : (
            <p className="muted">{t("storyboard.voiceAct.noText")}</p>
          )}
        </>
      )}

      {!editable && act.audioUrl ? (
        <div
          className="shot-voice-act-audio-preview"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <MediaPreview
            kind="audio"
            url={act.audioUrl}
            projectId={projectId}
            scriptId={scriptId}
            label={t("storyboard.previewTts")}
            className="shot-tts-preview"
          />
        </div>
      ) : null}

      {regenerateEnabled && !editable ? (
        <div className="shot-segment-card__actions" onClick={(e) => e.stopPropagation()}>
          <AssetRegenerateButton
            projectId={projectId}
            scriptId={scriptId}
            shotId={shotId}
            shotKinds={["tts"]}
            kind="tts"
            layout="compact"
            onDone={onRegenerateDone}
          />
        </div>
      ) : null}
    </article>
  );
}
