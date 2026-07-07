/** 解析 `/skillId 正文` 单轮 Skill 命令 */

export interface SkillOption {
  id: string;
  title: string;
  description: string;
  aliases?: string[];
}

export function parseSkillCommand(text: string): {
  skillId: string | null;
  userText: string;
  hasSlashPrefix: boolean;
} {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) {
    return { skillId: null, userText: trimmed, hasSlashPrefix: false };
  }
  const body = trimmed.slice(1).trim();
  if (!body) {
    return { skillId: null, userText: "", hasSlashPrefix: true };
  }
  const space = body.indexOf(" ");
  const token = (space === -1 ? body : body.slice(0, space)).trim().toLowerCase();
  const rest = space === -1 ? "" : body.slice(space + 1).trim();
  return { skillId: token || null, userText: rest, hasSlashPrefix: true };
}

/** 输入 `/` 且尚未选定 skill（无空格）时显示选择器。 */
export function getSkillPickerQuery(input: string): string | null {
  if (!input.startsWith("/")) return null;
  const afterSlash = input.slice(1);
  if (afterSlash.includes(" ")) return null;
  return afterSlash.toLowerCase();
}

export function filterSkills(
  skills: SkillOption[],
  query: string
): SkillOption[] {
  const q = query.trim().toLowerCase();
  if (!q) return skills;
  return skills.filter((skill) => {
    if (skill.id.includes(q)) return true;
    if (skill.title.toLowerCase().includes(q)) return true;
    return (skill.aliases ?? []).some(
      (alias) => alias.includes(q) || alias.toLowerCase().includes(q)
    );
  });
}

export function applySkillSelection(skillId: string): string {
  return `/${skillId} `;
}
