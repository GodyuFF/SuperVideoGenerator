/**
 * 剧本角色看板选项（配音幕角色选择器共用）。
 */

const API = "/api";

/** 看板角色项摘要。 */
export interface CharacterBoardOption {
  id: string;
  name: string;
  ttsVoice: string;
}

/** 从角色看板 API 拉取可选角色列表。 */
export async function fetchCharacterBoardOptions(
  projectId: string,
  scriptId: string,
): Promise<CharacterBoardOption[]> {
  const params = new URLSearchParams({ script_id: scriptId });
  const res = await fetch(`${API}/projects/${projectId}/board/character?${params}`);
  if (!res.ok) return [];
  const data = (await res.json()) as { items?: Record<string, unknown>[] };
  return (data.items ?? [])
    .map((item) => {
      const content = item.content as { tts_voice?: string } | undefined;
      return {
        id: String(item.id ?? item.asset_id ?? ""),
        name: String(item.name ?? item.id ?? ""),
        ttsVoice: String(content?.tts_voice ?? "").trim(),
      } satisfies CharacterBoardOption;
    })
    .filter((o) => o.id);
}

/** 按资产 ID 解析角色显示名。 */
export function resolveCharacterDisplayName(
  characterRef: string,
  options: CharacterBoardOption[],
  narratorLabel: string,
): string {
  const ref = characterRef.trim();
  if (!ref) return narratorLabel;
  const hit = options.find((o) => o.id === ref);
  if (hit) return hit.name;
  return ref;
}

/** 选中角色时写入的配音幕 patch（含角色音色）。 */
export function voiceActPatchForCharacter(
  characterRef: string,
  options: CharacterBoardOption[],
): { characterRef: string; voice: string } {
  const ref = characterRef.trim();
  if (!ref) {
    return { characterRef: "", voice: "" };
  }
  const hit = options.find((o) => o.id === ref);
  return {
    characterRef: ref,
    voice: hit?.ttsVoice ?? "",
  };
}
