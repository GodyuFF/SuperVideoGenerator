/**
 * 生图进度弹窗：展示 generate_images 并发任务的逐张状态。
 */

export type ImageGenItemStatus = "pending" | "started" | "completed" | "failed";

export interface ImageGenProgressItem {
  index: number;
  sourceTextAssetId: string;
  name: string;
  status: ImageGenItemStatus;
  url?: string;
  error?: string;
}

interface Props {
  open: boolean;
  stepId: string;
  total: number;
  items: ImageGenProgressItem[];
  onClose?: () => void;
}

function statusLabel(status: ImageGenItemStatus): string {
  switch (status) {
    case "pending":
      return "等待";
    case "started":
      return "生成中";
    case "completed":
      return "完成";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

/** 生图进度模态框 */
export function ImageGenProgressModal({
  open,
  stepId,
  total,
  items,
  onClose,
}: Props) {
  if (!open || total <= 0) return null;

  const completed = items.filter((i) => i.status === "completed").length;
  const failed = items.filter((i) => i.status === "failed").length;
  const done = completed + failed >= total;

  return (
    <div className="a2ui-overlay image-gen-overlay">
      <div className="a2ui-modal image-gen-modal" role="dialog" aria-modal="true">
        <header>
          <span className="a2ui-badge">image_gen</span>
          <h2>图片生成进度</h2>
        </header>
        <p className="a2ui-desc">
          步骤 {stepId || "—"} · {completed}/{total} 已完成
          {failed > 0 ? ` · ${failed} 失败` : ""}
        </p>
        <ul className="image-gen-list">
          {items.map((item) => (
            <li
              key={`${item.sourceTextAssetId}-${item.index}`}
              className={`image-gen-item image-gen-item--${item.status}`}
            >
              <span className="image-gen-item-name">{item.name}</span>
              <span className="image-gen-item-status">{statusLabel(item.status)}</span>
              {item.error && (
                <span className="image-gen-item-error" title={item.error}>
                  {item.error}
                </span>
              )}
            </li>
          ))}
        </ul>
        {done && onClose && (
          <footer className="a2ui-actions">
            <button type="button" className="btn-primary" onClick={onClose}>
              关闭
            </button>
          </footer>
        )}
      </div>
    </div>
  );
}
