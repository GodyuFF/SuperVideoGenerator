/**
 * 生成内容展示：剧本正文、文字资产、分镜与媒体产出。
 */

import type { PlanStep, TextAsset, VideoPlan, VideoPlanShot } from "../types";

const ASSET_TYPE_LABEL: Record<string, string> = {
  plot: "剧情",
  character: "人物",
  scene: "场景",
  prop: "道具",
  narration: "旁白",
};

function formatAssetBody(content: Record<string, unknown>): string {
  for (const key of ["text", "description", "appearance", "content"]) {
    const val = content[key];
    if (typeof val === "string" && val.trim()) return val.trim();
  }
  if (Object.keys(content).length === 0) return "";
  return JSON.stringify(content, null, 2);
}

function SimpleMarkdown({ text }: { text: string }) {
  return (
    <div className="simple-md">
      {text.split("\n").map((line, i) => {
        const trimmed = line.trimEnd();
        if (trimmed.startsWith("# ")) {
          return <h3 key={i} className="md-h3">{trimmed.slice(2)}</h3>;
        }
        if (trimmed.startsWith("## ")) {
          return <h4 key={i} className="md-h4">{trimmed.slice(3)}</h4>;
        }
        if (trimmed.startsWith("### ")) {
          return <h5 key={i} className="md-h5">{trimmed.slice(4)}</h5>;
        }
        if (!trimmed.trim()) {
          return <div key={i} className="md-gap" />;
        }
        return <p key={i} className="md-p">{trimmed}</p>;
      })}
    </div>
  );
}

function MediaOutputList({ steps }: { steps: PlanStep[] }) {
  const items = steps.flatMap((step) =>
    (step.outputs ?? []).map((o) => ({ ...o, stepTitle: step.title }))
  );
  if (items.length === 0) return null;

  return (
    <section className="content-section media-section">
      <h3>媒体产出</h3>
      <ul className="media-output-list">
        {items.map((item, i) => (
          <li key={`${item.asset_id}-${i}`} className={`media-output-item kind-${item.kind}`}>
            <span className="media-kind">{item.kind}</span>
            <strong>{item.label}</strong>
            <span className="muted media-step">{item.stepTitle}</span>
            {item.url ? (
              <a className="media-link" href={item.url} target="_blank" rel="noreferrer">
                {item.url}
              </a>
            ) : (
              <code className="media-id">{item.asset_id}</code>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ShotList({ shots }: { shots: VideoPlanShot[] }) {
  if (shots.length === 0) return null;
  const sorted = [...shots].sort((a, b) => a.order - b.order);
  return (
    <section className="content-section storyboard-section">
      <h3>分镜计划（{sorted.length} 镜）</h3>
      <ol className="shot-list">
        {sorted.map((shot) => (
          <li key={shot.id} className="shot-item">
            <div className="shot-header">
              <span className="shot-order">镜 {shot.order + 1}</span>
              <span className="shot-meta">
                {shot.duration_ms / 1000}s · {shot.camera_motion}
              </span>
            </div>
            {shot.narration_text && (
              <p className="shot-narration">{shot.narration_text}</p>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function AssetCards({ assets }: { assets: TextAsset[] }) {
  if (assets.length === 0) return null;
  const grouped = [...assets].sort((a, b) => a.type.localeCompare(b.type));

  return (
    <section className="content-section assets-detail-section">
      <h3>文字资产（{assets.length}）</h3>
      <div className="asset-cards">
        {grouped.map((asset) => {
          const body = formatAssetBody(asset.content);
          return (
            <article key={asset.id} className="asset-card">
              <header className="asset-card-header">
                <strong>{asset.name}</strong>
                <span className="asset-type-badge">
                  {ASSET_TYPE_LABEL[asset.type] ?? asset.type}
                </span>
                <span className="asset-scope-badge">{asset.scope}</span>
              </header>
              {body ? (
                <div className="asset-card-body">{body}</div>
              ) : (
                <p className="muted asset-empty">暂无正文</p>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

interface GeneratedContentProps {
  scriptTitle: string;
  scriptContentMd: string;
  assets: TextAsset[];
  videoPlan: VideoPlan | null;
  planSteps: PlanStep[];
}

export function GeneratedContent({
  scriptTitle,
  scriptContentMd,
  assets,
  videoPlan,
  planSteps,
}: GeneratedContentProps) {
  const hasScript = scriptContentMd.trim().length > 0;
  const hasAny =
    hasScript ||
    assets.length > 0 ||
    (videoPlan?.shots?.length ?? 0) > 0 ||
    planSteps.some((s) => (s.outputs?.length ?? 0) > 0);

  if (!hasAny) {
    return (
      <section className="content-section content-empty">
        <p className="muted">生成完成后，剧本、分镜与资产内容将显示在此处。</p>
      </section>
    );
  }

  return (
    <div className="generated-content">
      {hasScript && (
        <section className="content-section script-md-section">
          <h3>剧本正文</h3>
          {scriptTitle && <p className="script-title-line">{scriptTitle}</p>}
          <SimpleMarkdown text={scriptContentMd} />
        </section>
      )}

      {videoPlan && videoPlan.shots.length > 0 && (
        <ShotList shots={videoPlan.shots} />
      )}

      <AssetCards assets={assets} />

      <MediaOutputList steps={planSteps} />
    </div>
  );
}
