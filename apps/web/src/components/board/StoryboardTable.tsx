/**
 * 分镜计划稿表格：镜号、时间、旁白/对白、画面、运镜、配音。
 */

import { MediaPreview } from "../MediaPreview";
import type { BoardView } from "../../types/board";

/** 将毫秒格式化为 m:ss.s（与后端 time_label 一致）。 */
function formatMs(ms: number): string {
  const totalSec = Math.max(0, ms) / 1000;
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  const secStr = seconds.toFixed(1);
  const paddedSec = secStr.length >= 4 ? secStr : secStr.padStart(4, "0");
  return `${minutes}:${paddedSec}`;
}

interface StoryboardTableProps {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
}

/** 分镜 Tab 表格视图。 */
export function StoryboardTable({ board, projectId, scriptId }: StoryboardTableProps) {
  const items = board.items ?? [];
  if (items.length === 0) {
    return <p className="muted">分镜计划稿将在 storyboard_agent 完成后显示。</p>;
  }

  return (
    <div className="storyboard-table-wrap">
      <table className="storyboard-table">
        <thead>
          <tr>
            <th>镜号</th>
            <th>时间</th>
            <th>旁白 / 对白</th>
            <th>画面</th>
            <th>运镜</th>
            <th>配音</th>
          </tr>
        </thead>
        <tbody>
          {items.map((raw, index) => {
            const shot = raw as Record<string, unknown>;
            const startMs = Number(shot.start_ms ?? 0);
            const endMs = Number(shot.end_ms ?? startMs + Number(shot.duration_ms ?? 0));
            const timeLabel =
              typeof shot.time_label === "string" && shot.time_label
                ? shot.time_label
                : `${formatMs(startMs)} – ${formatMs(endMs)}`;
            const timelineSource =
              shot.timeline_source === "edit_timeline"
                ? "剪辑时间轴"
                : shot.timeline_source === "plan_estimate"
                  ? "计划估算"
                  : "";
            const durationMs = Number(shot.duration_ms ?? 0);
            const narration = String(shot.narration_text ?? "").trim();
            const subtitleLines = Array.isArray(shot.subtitle_lines)
              ? (shot.subtitle_lines as Array<Record<string, unknown>>)
              : [];
            const charNames = Array.isArray(shot.character_names)
              ? (shot.character_names as string[]).filter(Boolean)
              : [];
            const frameUrl = shot.frame_preview_url ? String(shot.frame_preview_url) : "";
            const frameName = shot.frame_asset_name ? String(shot.frame_asset_name) : "";
            const camera = String(shot.camera_motion ?? "static");
            const ttsUrl = shot.tts_audio_url ? String(shot.tts_audio_url) : "";

            return (
              <tr key={String(shot.id)}>
                <td className="storyboard-table-num">{Number(shot.order ?? index) + 1}</td>
                <td className="storyboard-table-time">
                  <span>{timeLabel}</span>
                  {timelineSource ? (
                    <span className="muted storyboard-table-duration">({timelineSource})</span>
                  ) : null}
                  <span className="muted storyboard-table-duration">({durationMs / 1000}s)</span>
                </td>
                <td className="storyboard-table-dialogue">
                  {charNames.length > 0 && (
                    <p className="storyboard-table-characters">
                      角色：{charNames.join("、")}
                    </p>
                  )}
                  {narration ? (
                    <p className="storyboard-table-narration">{narration}</p>
                  ) : (
                    <span className="muted">—</span>
                  )}
                  {subtitleLines.length > 0 && (
                    <ul className="storyboard-subtitle-lines muted">
                      {subtitleLines.map((line, lineIdx) => {
                        const absStart = Number(line.absolute_start_ms ?? line.start_ms ?? 0);
                        const absEnd = Number(line.absolute_end_ms ?? line.end_ms ?? absStart);
                        const text = String(line.text ?? "").trim();
                        if (!text) return null;
                        return (
                          <li key={`${String(shot.id)}-sub-${lineIdx}`}>
                            {formatMs(absStart)}–{formatMs(absEnd)} {text}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </td>
                <td className="storyboard-table-frame">
                  {frameUrl ? (
                    <MediaPreview
                      kind="image"
                      url={frameUrl}
                      label={frameName || "画面"}
                      projectId={projectId}
                      scriptId={scriptId}
                      className="storyboard-frame-preview"
                    />
                  ) : frameName ? (
                    <span className="muted">{frameName}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="storyboard-table-motion">{camera}</td>
                <td className="storyboard-table-tts">
                  {ttsUrl ? (
                    <MediaPreview
                      kind="audio"
                      url={ttsUrl}
                      label="试听"
                      projectId={projectId}
                      scriptId={scriptId}
                      className="shot-tts-preview"
                    />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
