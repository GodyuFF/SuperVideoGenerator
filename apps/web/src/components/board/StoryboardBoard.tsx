/**
 * 分镜看板容器：胶片条默认视图、紧凑表格切换、拖拽排序与结构编辑。
 */

import { useMemo, useState } from "react";
import { DragDropContext, Draggable, Droppable, type DropResult } from "@hello-pangea/dnd";
import { useAppTranslation } from "../../i18n/useAppTranslation";
import type { VideoPlanOp } from "../../types/videoPlan";
import { buildMinimalShotPayload } from "../../utils/shotTrackUtils";
import type { BoardView } from "../../types/board";
import { StoryboardShotCard } from "./StoryboardShotCard";
import { StoryboardTable } from "./StoryboardTable";
import {
  buildShotDetailItem,
  formatTotalDurationMs,
  loadStoryboardViewMode,
  parseStoryboardShots,
  saveStoryboardViewMode,
  type ShotDetailItem,
  type StoryboardViewMode,
} from "./storyboardShared";

interface StoryboardBoardProps {
  board: BoardView;
  projectId?: string | null;
  scriptId?: string | null;
  manualEditEnabled?: boolean;
  saving?: boolean;
  onOpenShot?: (shot: ShotDetailItem) => void;
  onApplyOps?: (ops: VideoPlanOp[]) => Promise<void>;
  onBoardRefresh?: () => void;
}

/** 分镜 Tab 主视图：胶片条 + 表格切换 + 编辑工具栏。 */
export function StoryboardBoard({
  board,
  projectId,
  scriptId,
  manualEditEnabled,
  saving,
  onOpenShot,
  onApplyOps,
  onBoardRefresh,
}: StoryboardBoardProps) {
  const { t } = useAppTranslation("board");
  const [viewMode, setViewMode] = useState<StoryboardViewMode>(loadStoryboardViewMode);
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const timelineLabels = useMemo(
    () => ({
      edit: t("storyboard.timelineEdit"),
      plan: t("storyboard.timelinePlan"),
    }),
    [t],
  );

  const shots = useMemo(() => {
    if (board.kind !== "storyboard") return [];
    return parseStoryboardShots(board, timelineLabels);
  }, [board, timelineLabels]);

  const totalDurationMs = useMemo(() => {
    if (shots.length === 0) return 0;
    return Math.max(...shots.map((s) => s.end_ms));
  }, [shots]);

  const handleViewChange = (mode: StoryboardViewMode) => {
    setViewMode(mode);
    saveStoryboardViewMode(mode);
  };

  /** 合并模式下勾选镜头；否则打开详情抽屉。 */
  const handleShotActivate = (shot: (typeof shots)[number]) => {
    if (mergeMode && onApplyOps) {
      setMergeSelection((prev) =>
        prev.includes(shot.id) ? prev.filter((id) => id !== shot.id) : [...prev, shot.id],
      );
      return;
    }
    onOpenShot?.(buildShotDetailItem(shot));
  };

  const shotCardInteractive = Boolean((mergeMode && onApplyOps) || onOpenShot);

  const runOps = async (ops: VideoPlanOp[]) => {
    if (!onApplyOps) return;
    try {
      await onApplyOps(ops);
      setStatusMsg(null);
      onBoardRefresh?.();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const handleAddShot = () => {
    const afterOrder = Math.max(0, shots.length - 1);
    void runOps([
      {
        op: "add",
        after_order: afterOrder,
        new_shot: buildMinimalShotPayload(shots.length, 3000, "", "static"),
      },
    ]);
  };

  const handleMerge = () => {
    if (mergeSelection.length < 2) {
      setStatusMsg(t("storyboard.edit.mergeNeedTwo"));
      return;
    }
    void runOps([{ op: "merge", shot_ids: mergeSelection }]).then(() => {
      setMergeSelection([]);
      setMergeMode(false);
    });
  };

  const handleDragEnd = (result: DropResult) => {
    if (!result.destination || !onApplyOps) return;
    const items = [...shots];
    const [removed] = items.splice(result.source.index, 1);
    items.splice(result.destination.index, 0, removed);
    void runOps([{ op: "reorder", ordered_shot_ids: items.map((s) => s.id) }]);
  };

  const editHref =
    projectId && scriptId
      ? `#/project/${projectId}/script/${scriptId}/edit`
      : undefined;

  if (shots.length === 0) {
    return (
      <div className="storyboard-board">
        <p className="muted">{t("storyboard.empty")}</p>
        {manualEditEnabled && onApplyOps ? (
          <button type="button" className="btn-primary btn-sm" disabled={saving} onClick={handleAddShot}>
            {t("storyboard.edit.addShot")}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="storyboard-board">
      <div className="storyboard-toolbar">
        <div className="storyboard-toolbar__summary">
          <span className="storyboard-toolbar__count">
            {t("storyboard.shotCount", { count: shots.length })}
          </span>
          <span className="storyboard-toolbar__duration tabular-nums">
            {t("storyboard.totalDuration", {
              duration: formatTotalDurationMs(totalDurationMs),
            })}
          </span>
        </div>
        <div className="storyboard-toolbar__actions">
          {manualEditEnabled && onApplyOps ? (
            <>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={saving}
                onClick={handleAddShot}
              >
                {t("storyboard.edit.addShot")}
              </button>
              <button
                type="button"
                className={`btn-secondary btn-sm${mergeMode ? " active" : ""}`}
                disabled={saving}
                onClick={() => {
                  setMergeMode((v) => !v);
                  setMergeSelection([]);
                }}
              >
                {t("storyboard.edit.mergeMode")}
              </button>
              {mergeMode ? (
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  disabled={saving || mergeSelection.length < 2}
                  onClick={handleMerge}
                >
                  {t("storyboard.edit.merge", { count: mergeSelection.length })}
                </button>
              ) : null}
            </>
          ) : null}
          <div className="storyboard-view-toggle" role="group" aria-label={t("storyboard.viewToggle")}>
            <button
              type="button"
              className={`btn-secondary btn-sm${viewMode === "filmstrip" ? " active" : ""}`}
              aria-pressed={viewMode === "filmstrip"}
              onClick={() => handleViewChange("filmstrip")}
            >
              {t("storyboard.viewFilmstrip")}
            </button>
            <button
              type="button"
              className={`btn-secondary btn-sm${viewMode === "table" ? " active" : ""}`}
              aria-pressed={viewMode === "table"}
              onClick={() => handleViewChange("table")}
            >
              {t("storyboard.viewTable")}
            </button>
          </div>
          {editHref ? (
            <a className="btn-secondary btn-sm" href={editHref}>
              {t("storyboard.openEdit")}
            </a>
          ) : null}
        </div>
      </div>

      {statusMsg ? <p className="form-error">{statusMsg}</p> : null}
      {mergeMode ? <p className="muted">{t("storyboard.edit.mergeHint")}</p> : null}

      {viewMode === "filmstrip" ? (
        manualEditEnabled && onApplyOps && !mergeMode ? (
          <DragDropContext onDragEnd={handleDragEnd}>
            <Droppable droppableId="storyboard-filmstrip" direction="vertical">
              {(provided) => (
                <div
                  className="storyboard-filmstrip"
                  ref={provided.innerRef}
                  {...provided.droppableProps}
                >
                  {shots.map((shot, index) => (
                    <Draggable key={shot.id} draggableId={shot.id} index={index}>
                      {(dragProvided, snapshot) => (
                        <div
                          ref={dragProvided.innerRef}
                          {...dragProvided.draggableProps}
                          className={`storyboard-filmstrip-item${
                            snapshot.isDragging ? " storyboard-filmstrip-item--dragging" : ""
                          }`}
                        >
                          <span
                            className="storyboard-drag-handle"
                            {...dragProvided.dragHandleProps}
                            aria-label={t("storyboard.edit.dragHandle")}
                          >
                            ⋮⋮
                          </span>
                          <StoryboardShotCard
                            shot={shot}
                            displayIndex={shot.displayNumber}
                            projectId={projectId}
                            scriptId={scriptId}
                            mergeMode={false}
                            mergeSelected={false}
                            onOpen={shotCardInteractive ? handleShotActivate : undefined}
                          />
                        </div>
                      )}
                    </Draggable>
                  ))}
                  {provided.placeholder}
                </div>
              )}
            </Droppable>
          </DragDropContext>
        ) : (
          <div className="storyboard-filmstrip">
            {shots.map((shot) => (
              <div
                key={shot.id}
                className={`storyboard-filmstrip-item${
                  mergeMode && mergeSelection.includes(shot.id)
                    ? " storyboard-filmstrip-item--selected"
                    : ""
                }`}
              >
                <StoryboardShotCard
                  shot={shot}
                  displayIndex={shot.displayNumber}
                  projectId={projectId}
                  scriptId={scriptId}
                  mergeMode={mergeMode}
                  mergeSelected={mergeSelection.includes(shot.id)}
                  onOpen={shotCardInteractive ? handleShotActivate : undefined}
                />
              </div>
            ))}
          </div>
        )
      ) : (
        <StoryboardTable
          shots={shots}
          projectId={projectId}
          scriptId={scriptId}
          mergeMode={mergeMode}
          mergeSelection={mergeSelection}
          onOpenShot={shotCardInteractive ? handleShotActivate : undefined}
        />
      )}
    </div>
  );
}
