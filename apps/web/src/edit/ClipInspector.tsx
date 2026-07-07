import { useRef, useState } from "react";
import {
  ANIMATION_PRESETS,
  applyAnimationPreset,
  keyframeAtPlayhead,
} from "./animationPresets";
import type { ClipKeyframe, ClipTransform, EditCapabilities, TrackClip } from "./types";
import { DEFAULT_TRANSFORM } from "./types";

interface ClipInspectorProps {
  clip: TrackClip | null;
  capabilities: EditCapabilities | null;
  editable: boolean;
  playheadMs?: number;
  selectedKeyframeIdx?: number | null;
  onKeyframeSelect?: (idx: number | null) => void;
  onChange: (patch: Partial<TrackClip>) => void;
}

function numField(
  label: string,
  value: number,
  disabled: boolean,
  onChange: (v: number) => void,
  step = "0.01"
) {
  return (
    <label>
      {label}
      <input
        type="number"
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function patchKeyframeField(
  kfs: ClipKeyframe[],
  idx: number,
  patch: Partial<ClipKeyframe>
): ClipKeyframe[] {
  const next = [...kfs];
  next[idx] = { ...next[idx], ...patch };
  return next.sort((a, b) => (a.time_ms ?? 0) - (b.time_ms ?? 0));
}

export function ClipInspector({
  clip,
  capabilities,
  editable,
  playheadMs = 0,
  selectedKeyframeIdx,
  onKeyframeSelect,
  onChange,
}: ClipInspectorProps) {
  const [presetId, setPresetId] = useState(ANIMATION_PRESETS[0]?.id ?? "fade_in");
  const keyframeRowRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  if (!clip) {
    return <p className="muted">选中时间轴片段以编辑属性。</p>;
  }

  const activeClip: TrackClip = clip;
  const motions = capabilities?.motions ?? [];
  const transitions = capabilities?.transitions ?? [];
  const backgrounds = capabilities?.backgrounds ?? [];
  const maxTransitionMs = capabilities?.transition_max_duration_ms ?? 2000;
  const tr: ClipTransform = { ...DEFAULT_TRANSFORM, ...activeClip.transform };
  const clipDuration = Math.max(
    Number(activeClip.end_ms ?? 0) - Number(activeClip.start_ms ?? 0),
    1
  );

  function patchTransform(patch: Partial<ClipTransform>) {
    onChange({ transform: { ...tr, ...patch } });
  }

  function addKeyframe() {
    const kfs: ClipKeyframe[] = [...(tr.keyframes ?? [])];
    kfs.push({
      time_ms: 0,
      x: tr.x,
      y: tr.y,
      width: tr.width,
      height: tr.height,
      opacity: tr.opacity,
      rotation: tr.rotation,
    });
    patchTransform({ keyframes: kfs.sort((a, b) => (a.time_ms ?? 0) - (b.time_ms ?? 0)) });
  }

  function addKeyframeAtPlayhead() {
    const { keyframes, index } = keyframeAtPlayhead(activeClip, playheadMs, tr);
    patchTransform({ keyframes });
    onKeyframeSelect?.(index);
    const row = keyframeRowRefs.current.get(index);
    row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function writeTransformToSelectedKeyframe() {
    if (selectedKeyframeIdx == null || !(tr.keyframes ?? [])[selectedKeyframeIdx]) return;
    const next = patchKeyframeField(tr.keyframes ?? [], selectedKeyframeIdx, {
      x: tr.x,
      y: tr.y,
      width: tr.width,
      height: tr.height,
      opacity: tr.opacity,
      rotation: tr.rotation,
    });
    patchTransform({ keyframes: next });
  }

  function applyPreset() {
    const patch = applyAnimationPreset(activeClip, presetId, clipDuration);
    onChange(patch);
  }

  return (
    <div className="edit-studio-inspector">
      <label>
        标签
        <input
          type="text"
          value={activeClip.label ?? ""}
          disabled={!editable}
          onChange={(e) => onChange({ label: e.target.value })}
        />
      </label>
      <label>
        开始 (ms)
        <input
          type="number"
          value={clip.start_ms ?? 0}
          disabled={!editable}
          onChange={(e) => onChange({ start_ms: Number(e.target.value) })}
        />
      </label>
      <label>
        结束 (ms)
        <input
          type="number"
          value={clip.end_ms ?? 0}
          disabled={!editable}
          onChange={(e) => onChange({ end_ms: Number(e.target.value) })}
        />
      </label>
      {clip.track === "video" && (
        <>
          <fieldset className="edit-studio-fieldset">
            <legend>画布位置（0–1）</legend>
            {numField("中心 X", tr.x ?? 0.5, !editable, (v) => patchTransform({ x: v }))}
            {numField("中心 Y", tr.y ?? 0.5, !editable, (v) => patchTransform({ y: v }))}
            {numField("宽度", tr.width ?? 1, !editable, (v) => patchTransform({ width: v }))}
            {numField("高度", tr.height ?? 1, !editable, (v) => patchTransform({ height: v }))}
            <label>
              统一缩放
              <input
                type="range"
                min={0.05}
                max={1}
                step={0.01}
                value={Math.min(tr.width ?? 1, tr.height ?? 1)}
                disabled={!editable}
                onChange={(e) => {
                  const s = Number(e.target.value);
                  patchTransform({ width: s, height: s });
                }}
              />
            </label>
            {numField("不透明度", tr.opacity ?? 1, !editable, (v) => patchTransform({ opacity: v }))}
            {numField("旋转 (°)", tr.rotation ?? 0, !editable, (v) => patchTransform({ rotation: v }), "1")}
          </fieldset>
          <div className="edit-studio-inspector-row edit-studio-preset-row">
            <label>
              动画预设
              <select
                value={presetId}
                disabled={!editable}
                onChange={(e) => setPresetId(e.target.value)}
              >
                {ANIMATION_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            {editable && (
              <button type="button" className="btn-secondary btn-sm" onClick={applyPreset}>
                应用预设
              </button>
            )}
          </div>
          <div className="edit-studio-inspector-row">
            <label>
              运镜
              <select
                value={clip.motion ?? "ken_burns_in"}
                disabled={!editable}
                onChange={(e) => onChange({ motion: e.target.value })}
              >
                {motions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label>
              转场入
              <select
                value={clip.transition_in?.type ?? "cut"}
                disabled={!editable}
                onChange={(e) =>
                  onChange({
                    transition_in: {
                      type: e.target.value,
                      duration_ms: clip.transition_in?.duration_ms ?? 0,
                    },
                  })
                }
              >
                {transitions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label>
              入时长 (ms)
              <input
                type="number"
                min={0}
                max={maxTransitionMs}
                value={clip.transition_in?.duration_ms ?? 0}
                disabled={!editable}
                onChange={(e) =>
                  onChange({
                    transition_in: {
                      type: clip.transition_in?.type ?? "cut",
                      duration_ms: Number(e.target.value),
                    },
                  })
                }
              />
            </label>
            <label>
              转场出
              <select
                value={clip.transition_out?.type ?? "cut"}
                disabled={!editable}
                onChange={(e) =>
                  onChange({
                    transition_out: {
                      type: e.target.value,
                      duration_ms: clip.transition_out?.duration_ms ?? 0,
                    },
                  })
                }
              >
                {transitions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label>
              出时长 (ms)
              <input
                type="number"
                min={0}
                max={maxTransitionMs}
                value={clip.transition_out?.duration_ms ?? 0}
                disabled={!editable}
                onChange={(e) =>
                  onChange({
                    transition_out: {
                      type: clip.transition_out?.type ?? "cut",
                      duration_ms: Number(e.target.value),
                    },
                  })
                }
              />
            </label>
            <label>
              背景
              <select
                value={clip.background?.type ?? "solid"}
                disabled={!editable}
                onChange={(e) =>
                  onChange({
                    background: {
                      type: e.target.value,
                      color: clip.background?.color ?? "#0f172a",
                      asset_ref: clip.background?.asset_ref,
                    },
                  })
                }
              >
                {backgrounds.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="edit-studio-keyframes">
            <strong>关键帧</strong>
            {editable && (
              <>
                <button type="button" className="btn-secondary btn-sm" onClick={addKeyframeAtPlayhead}>
                  播放头打帧
                </button>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={selectedKeyframeIdx == null}
                  onClick={writeTransformToSelectedKeyframe}
                >
                  写入选中帧
                </button>
              </>
            )}
            {(tr.keyframes ?? []).map((kf, idx) => (
              <div
                key={idx}
                ref={(el) => {
                  if (el) keyframeRowRefs.current.set(idx, el);
                }}
                className={`edit-studio-keyframe-row ${selectedKeyframeIdx === idx ? "selected" : ""}`}
                onClick={() => onKeyframeSelect?.(idx)}
              >
                {numField("t", kf.time_ms ?? 0, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { time_ms: v }) })
                , "1")}
                {numField("x", kf.x ?? tr.x ?? 0.5, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { x: v }) })
                )}
                {numField("y", kf.y ?? tr.y ?? 0.5, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { y: v }) })
                )}
                {numField("w", kf.width ?? tr.width ?? 1, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { width: v }) })
                )}
                {numField("h", kf.height ?? tr.height ?? 1, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { height: v }) })
                )}
                {numField("α", kf.opacity ?? tr.opacity ?? 1, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { opacity: v }) })
                )}
                {numField("∠", kf.rotation ?? tr.rotation ?? 0, !editable, (v) =>
                  patchTransform({ keyframes: patchKeyframeField(tr.keyframes ?? [], idx, { rotation: v }) })
                , "1")}
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={!editable}
                  onClick={(e) => {
                    e.stopPropagation();
                    const next = (tr.keyframes ?? []).filter((_, i) => i !== idx);
                    patchTransform({ keyframes: next });
                    if (selectedKeyframeIdx === idx) onKeyframeSelect?.(null);
                  }}
                >
                  删
                </button>
              </div>
            ))}
            {editable && (
              <button type="button" className="btn-secondary btn-sm" onClick={addKeyframe}>
                + 关键帧
              </button>
            )}
          </div>
        </>
      )}
      <label className="edit-studio-inspector-wide">
        描述
        <textarea
          value={clip.edit_description ?? ""}
          disabled={!editable}
          rows={3}
          onChange={(e) => onChange({ edit_description: e.target.value })}
        />
      </label>
    </div>
  );
}
