/**
 * 生图进度内联展示：嵌入 Plan 步骤卡片，逐张显示 generate_images 任务状态。
 */

import { MediaPreview } from "./MediaPreview";

export type ImageGenItemStatus = "pending" | "started" | "completed" | "failed";

/** 单张生图任务的前端进度条目。 */
export interface ImageGenProgressItem {
  index: number;
  sourceTextAssetId: string;
  name: string;
  status: ImageGenItemStatus;
  url?: string;
  error?: string;
}

interface Props {
  total: number;
  items: ImageGenProgressItem[];
  projectId?: string | null;
  scriptId?: string | null;
}

/** 生图条目状态文案。 */
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

/** Plan 步骤内的生图进度列表。 */
export function ImageGenProgressInline({
  total,
  items,
  projectId,
  scriptId,
}: Props) {
  if (total <= 0) return null;

  const completed = items.filter((i) => i.status === "completed").length;
  const failed = items.filter((i) => i.status === "failed").length;

  return (
    <div className="plan-step-image-gen">
      <div className="plan-step-image-gen-summary muted">
        图片生成 · {completed}/{total} 已完成
        {failed > 0 ? ` · ${failed} 失败` : ""}
      </div>
      <ul className="image-gen-list image-gen-list--inline">
        {items.map((item) => (
          <li
            key={`${item.sourceTextAssetId}-${item.index}`}
            className={`image-gen-item image-gen-item--${item.status}`}
          >
            <div className="image-gen-item-main">
              <span className="image-gen-item-name">{item.name}</span>
              <span className="image-gen-item-status">{statusLabel(item.status)}</span>
              {item.error && (
                <span className="image-gen-item-error" title={item.error}>
                  {item.error}
                </span>
              )}
            </div>
            {item.url && item.status === "completed" && (
              <MediaPreview
                kind="image"
                url={item.url}
                label={item.name}
                projectId={projectId}
                scriptId={scriptId}
                className="image-gen-item-preview"
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
