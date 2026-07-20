/** 剧本页人工增删改资产 API */

const API = "/api";

export async function generateTextAssetDraft(
  projectId: string,
  scriptId: string,
  body: {
    asset_type: string;
    summary: string;
    name?: string;
    hints?: Record<string, unknown>;
  },
) {
  const r = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/assets/generate-draft`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new Error(String(data.detail ?? `AI 生成失败 (${r.status})`));
  }
  return r.json() as Promise<{ name: string; content: Record<string, unknown> }>;
}

export async function createTextAsset(
  projectId: string,
  scriptId: string,
  body: { type: string; name: string; content?: Record<string, unknown> }
) {
  const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}/assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new Error(String(data.detail ?? `创建失败 (${r.status})`));
  }
  return r.json();
}

export async function deleteTextAsset(
  projectId: string,
  scriptId: string,
  assetId: string
) {
  const r = await fetch(
    `${API}/projects/${projectId}/scripts/${scriptId}/assets/${assetId}`,
    { method: "DELETE" }
  );
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    const detail = data.detail;
    const message =
      typeof detail === "object" && detail && "message" in detail
        ? String((detail as { message?: string }).message)
        : typeof detail === "string"
          ? detail
          : `删除失败 (${r.status})`;
    throw new Error(message);
  }
  return r.json();
}

export async function patchScript(
  projectId: string,
  scriptId: string,
  body: { title?: string; content_md?: string; duration_sec?: number }
) {
  const r = await fetch(`${API}/projects/${projectId}/scripts/${scriptId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new Error(String(data.detail ?? `保存失败 (${r.status})`));
  }
  return r.json();
}
