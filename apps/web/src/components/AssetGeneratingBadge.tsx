/**
 * 资产/分镜「生成中」状态徽章。
 */

import { useAppTranslation } from "../i18n/useAppTranslation";
import type { AssetGenerationEntry } from "../utils/assetGenerationStatus";

interface AssetGeneratingBadgeProps {
  entry: AssetGenerationEntry;
  /** compact 用于卡片角标，inline 用于详情顶栏。 */
  variant?: "compact" | "inline";
  className?: string;
}

/** 按生成类型返回 i18n 键。 */
function labelKeyForKind(kind: AssetGenerationEntry["kind"]): string {
  if (kind === "image" || kind === "frame") return "generating.image";
  if (kind === "tts") return "generating.tts";
  if (kind === "video") return "generating.video";
  return "generating.default";
}

/** 展示生成中或失败状态的取景器徽章。 */
export function AssetGeneratingBadge({
  entry,
  variant = "compact",
  className = "",
}: AssetGeneratingBadgeProps) {
  const { t } = useAppTranslation("common");
  const isFailed = entry.phase === "failed";
  const classes = [
    "asset-gen-badge",
    variant === "inline" ? "asset-gen-badge--inline" : "asset-gen-badge--compact",
    isFailed ? "asset-gen-badge--failed" : "asset-gen-badge--active",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const text = isFailed ? t("generating.failed") : t(labelKeyForKind(entry.kind));

  return (
    <span className={classes} role="status" aria-live="polite">
      {!isFailed ? <span className="asset-gen-badge__pulse" aria-hidden="true" /> : null}
      <span className="asset-gen-badge__text">{text}</span>
    </span>
  );
}
