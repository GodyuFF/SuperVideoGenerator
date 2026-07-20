/**
 * 生成内容展示：剧本正文、文字资产、分镜与媒体产出。
 */

import type { PlanStep, TextAsset, VideoPlan, VideoPlanShot } from "../types";
import { shotCameraMotion, shotVoiceText } from "../utils/shotTrackUtils";
import type { MediaAsset } from "../types/agents";
import { MediaPreview } from "./MediaPreview";
import {
  ImageTextAssetCard,
  isImageTextAssetType,
} from "./ImageTextAssetCard";
import { resolveMediaPlayUrl } from "../utils/mediaUrl";

const ASSET_TYPE_LABEL: Record<string, string> = {
  plot: "剧情",
  character: "人物",
  scene: "空镜",
  prop: "道具",
  narration: "旁白",
};

function formatAssetBody(content: Record<string, unknown>): string {
  for (const key of ["summary", "text", "description", "appearance", "content"]) {
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

function isPlaceholderMediaUrl(url: string | undefined): boolean {
  if (!url || !url.trim()) return true;
  const u = url.trim().toLowerCase();
  if (u.includes("example.com")) return true;
  if (u.startsWith("/assets/")) return true;
  return false;
}

function StoredMediaList({
  items,
  projectId,
  scriptId,
}: {
  items: MediaAsset[];
  projectId?: string | null;
  scriptId?: string | null;
}) {
  const visible = items.filter((m) => !isPlaceholderMediaUrl(m.url));
  if (visible.length === 0) return null;

  const typeLabel: Record<string, string> = {
    image: "图片",
    video: "视频",
    audio: "配音",
    final: "成片",
  };

  return (
    <section className="content-section media-section stored-media-section">
      <h3>数字资产库（{visible.length}）</h3>
      <ul className="media-output-list">
        {visible.map((item) => {
          const playUrl = resolveMediaPlayUrl(item.url, projectId, scriptId);
          return (
          <li key={item.id} className={`media-output-item kind-${item.type}`}>
            <span className="media-kind">{typeLabel[item.type] ?? item.type}</span>
            <strong>{item.name}</strong>
            <MediaPreview
              kind={item.type}
              url={playUrl || item.url}
              label={item.type === "audio" ? "试听" : undefined}
              projectId={projectId}
              scriptId={scriptId}
            />
            {playUrl ? (
              <a className="media-link" href={playUrl} target="_blank" rel="noreferrer">
                {playUrl}
              </a>
            ) : item.url ? (
              <span className="muted">{item.url}</span>
            ) : (
              <code className="media-id">{item.id}</code>
            )}
          </li>
          );
        })}
      </ul>
    </section>
  );
}

function MediaOutputList({
  steps,
  projectId,
  scriptId,
}: {
  steps: PlanStep[];
  projectId?: string | null;
  scriptId?: string | null;
}) {
  const items = steps
    .flatMap((step) =>
      (step.outputs ?? []).map((o) => ({ ...o, stepTitle: step.title }))
    )
    .filter((item) => !isPlaceholderMediaUrl(item.url));

  if (items.length === 0) {
    const hasMediaSteps = steps.some((s) =>
      (s.outputs ?? []).some((o) => o.kind === "image" || o.kind === "video" || o.kind === "audio")
    );
    if (!hasMediaSteps) return null;
    return (
      <section className="content-section media-section">
        <h3>媒体产出</h3>
        <p className="muted media-unavailable-hint">
          媒体生成尚未接入，当前仅展示文字资产与分镜。
        </p>
      </section>
    );
  }

  return (
    <section className="content-section media-section">
      <h3>媒体产出</h3>
      <ul className="media-output-list">
        {items.map((item, i) => {
          const playUrl = resolveMediaPlayUrl(item.url, projectId, scriptId);
          return (
          <li key={`${item.asset_id}-${i}`} className={`media-output-item kind-${item.kind}`}>
            <span className="media-kind">{item.kind}</span>
            <strong>{item.label}</strong>
            <span className="muted media-step">{item.stepTitle}</span>
            <MediaPreview
              kind={item.kind}
              url={playUrl || item.url}
              projectId={projectId}
              scriptId={scriptId}
            />
            {playUrl ? (
              <a className="media-link" href={playUrl} target="_blank" rel="noreferrer">
                {playUrl}
              </a>
            ) : item.url ? (
              <span className="muted">{item.url}</span>
            ) : (
              <code className="media-id">{item.asset_id}</code>
            )}
          </li>
          );
        })}
      </ul>
    </section>
  );
}

function ShotList({ shots }: { shots: VideoPlanShot[] }) {
  if (shots.length === 0) return null;
  const sorted = [...shots].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  return (
    <section className="content-section storyboard-section">
      <h3>分镜计划（{sorted.length} 镜）</h3>
      <ol className="shot-list">
        {sorted.map((shot, index) => {
          const narr = shotVoiceText(shot);
          const motion = shotCameraMotion(shot);
          return (
          <li key={shot.id} className="shot-item">
            <div className="shot-header">
              <span className="shot-order">镜 {index + 1}</span>
              <span className="shot-meta">
                {(shot.duration_ms ?? 0) / 1000}s · {motion}
              </span>
            </div>
            {narr ? (
              <p className="shot-narration">{narr}</p>
            ) : null}
          </li>
          );
        })}
      </ol>
    </section>
  );
}

function AssetCards({ assets }: { assets: TextAsset[] }) {
  if (assets.length === 0) return null;
  const imageText = assets.filter((a) => isImageTextAssetType(a.type));
  const textOnly = assets.filter((a) => !isImageTextAssetType(a.type));
  const grouped = [...textOnly].sort((a, b) => a.type.localeCompare(b.type));

  return (
    <>
      {imageText.length > 0 && (
        <section className="content-section assets-detail-section">
          <h3>图文资产（{imageText.length}）</h3>
          <div className="asset-cards image-text-cards">
            {imageText.map((asset) => {
              const c = asset.content ?? {};
              const traits: Record<string, string> = {};
              for (const [k, v] of Object.entries(c)) {
                if (typeof v === "string" && v.trim() && k !== "description" && k !== "summary") {
                  if (!["image_prompt", "negative_prompt", "prompt_hint", "visual_style", "color_palette", "notes", "display_mode", "prompt_version", "prompt_locked", "tags"].includes(k)) {
                    traits[k] = v;
                  }
                }
              }
              return (
              <ImageTextAssetCard
                key={asset.id}
                item={{
                  id: asset.id,
                  type: asset.type,
                  name: asset.name,
                  scope: asset.scope,
                  content: c,
                  description: String(c.description ?? ""),
                  summary: String(c.summary ?? ""),
                  visual_style: String(c.visual_style ?? ""),
                  color_palette: String(c.color_palette ?? ""),
                  prompt_hint: String(c.prompt_hint ?? ""),
                  image_prompt: String(c.image_prompt ?? ""),
                  negative_prompt: String(c.negative_prompt ?? ""),
                  notes: String(c.notes ?? ""),
                  tags: Array.isArray(c.tags) ? (c.tags as string[]) : [],
                  display_mode: String(c.display_mode ?? "static_image"),
                  traits,
                }}
              />
            );})}
          </div>
        </section>
      )}
      {grouped.length > 0 && (
    <section className="content-section assets-detail-section">
      <h3>文字资产（{grouped.length}）</h3>
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
      )}
    </>
  );
}

interface GeneratedContentProps {
  scriptTitle: string;
  scriptContentMd: string;
  assets: TextAsset[];
  mediaAssets: MediaAsset[];
  videoPlan: VideoPlan | null;
  planSteps: PlanStep[];
  projectId?: string | null;
  scriptId?: string | null;
}

export function GeneratedContent({
  scriptTitle,
  scriptContentMd,
  assets,
  mediaAssets,
  videoPlan,
  planSteps,
  projectId,
  scriptId,
}: GeneratedContentProps) {
  const hasScript = scriptContentMd.trim().length > 0;
  const hasAny =
    hasScript ||
    assets.length > 0 ||
    mediaAssets.length > 0 ||
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

      {videoPlan?.shots && videoPlan.shots.length > 0 ? (
        <ShotList shots={videoPlan.shots} />
      ) : null}

      <AssetCards assets={assets} />

      <StoredMediaList items={mediaAssets} projectId={projectId} scriptId={scriptId} />

      <MediaOutputList steps={planSteps} projectId={projectId} scriptId={scriptId} />
    </div>
  );
}
