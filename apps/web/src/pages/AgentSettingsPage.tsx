/**
 * Agent 提示词工作台：风格/Profile CRUD、role/hint 编辑、工具勾选。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAgentConfig } from "../hooks/useAgentConfig";
import { useProject } from "../hooks/useApi";
import type {
  AgentConfigPatch,
  AgentInfo,
  AgentPromptContentOverride,
  AgentToolOption,
  AgentToolOverride,
  CustomAgentDefinition,
  CustomPromptProfile,
  StyleModeOption,
  StyleVideoGenMode,
  PromptProfileOption,
  SkillMetaItem,
} from "../types/agentConfig";
import { LocaleSwitcher } from "../i18n/LocaleSwitcher";
import { ThemeToggle } from "../components/theme/ThemeToggle";
import { AppShell } from "../components/layout/AppShell";
import { ResizableDrawerEdge } from "../components/layout/ResizableDrawerEdge";
import { layoutAgentToolCatalog } from "../lib/groupAgentTools";
import { normalizeStyleModeOptions, REMOVED_STYLE_MODE_IDS } from "../constants";
import { useResizableDrawerWidth } from "../hooks/useResizableDrawerWidth";
import { ToolSchemaDetailPanel } from "../components/agentWorkbench/ToolSchemaDetailPanel";
import "../styles/agent-workbench.css";

const API = "/api";

interface AgentSettingsPageProps {
  onBack: () => void;
  /** 打开 Skill 库管理页。 */
  onOpenSkills?: () => void;
}

type WorkbenchTab = "modes" | "agents";

const BUILTIN_STYLE_TEMPLATES = ["storybook", "ai_video", "frame_i2v"] as const;

/** 自定义风格可选的 AI 生视频子模式。 */
const STYLE_VIDEO_OPTIONS: StyleVideoGenMode[] = ["text2video", "img2video", "keyframes"];

const MASTER_AGENT_ID = "super_video_master";

/** 可克隆为自定义 Agent 的内置子 Agent。 */
const CLONABLE_AGENT_TEMPLATES = [
  "script_agent",
  "image_agent",
  "storyboard_agent",
  "storyboard_refine_agent",
  "video_agent",
  "tts_agent",
  "editing_agent",
] as const;

/** 各 Agent 在侧栏的缩写与主题色。 */
const AGENT_VISUAL: Record<string, { initials: string; accent: string }> = {
  super_video_master: { initials: "MV", accent: "#e0634a" },
  script_agent: { initials: "SC", accent: "#c9a227" },
  image_agent: { initials: "IM", accent: "#a78bfa" },
  storyboard_agent: { initials: "SB", accent: "#6b9fd4" },
  storyboard_refine_agent: { initials: "SR", accent: "#5ec4b0" },
  video_agent: { initials: "VD", accent: "#f472b6" },
  tts_agent: { initials: "TT", accent: "#4dbb8a" },
  editing_agent: { initials: "ED", accent: "#94a3b8" },
};

/** 取 Agent 侧栏视觉配置。 */
function agentVisual(name: string) {
  return AGENT_VISUAL[name] ?? { initials: name.slice(0, 2).toUpperCase(), accent: "#e0634a" };
}

/** Agent 配置页：全局提示词、风格与工具管理。 */
export function AgentSettingsPage({ onBack, onOpenSkills }: AgentSettingsPageProps) {
  const { t } = useTranslation();
  const { projectId } = useProject();
  const {
    config,
    styleModes,
    toolsCatalog,
    loading,
    error,
    refresh,
    update,
    fetchPrompt,
    fetchAgentsForProfile,
    restoreBuiltinProfile,
    restoreAllBuiltinProfiles,
  } = useAgentConfig(projectId);

  const [activeTab, setActiveTab] = useState<WorkbenchTab>("agents");
  const [profiles, setProfiles] = useState<Record<string, string>>({});
  const [customProfiles, setCustomProfiles] = useState<CustomPromptProfile[]>([]);
  const [customStyles, setCustomStyles] = useState<StyleModeOption[]>([]);
  const [customAgents, setCustomAgents] = useState<CustomAgentDefinition[]>([]);
  const [profileAgents, setProfileAgents] = useState<Record<string, string[]>>({});
  const [promptContent, setPromptContent] = useState<
    Record<string, Record<string, AgentPromptContentOverride>>
  >({});
  const [toolOverridesByProfile, setToolOverridesByProfile] = useState<
    Record<string, Record<string, AgentToolOverride>>
  >({});
  const [skillAllowlistsByProfile, setSkillAllowlistsByProfile] = useState<
    Record<string, Record<string, string[]>>
  >({});
  const [skillCatalog, setSkillCatalog] = useState<SkillMetaItem[]>([]);

  const [selectedProfile, setSelectedProfile] = useState<string>("");
  const [agentsForProfile, setAgentsForProfile] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const [roleDraft, setRoleDraft] = useState("");
  const [hintDraft, setHintDraft] = useState("");
  const [promptSource, setPromptSource] = useState<{ role_prompt: string; action_hint: string }>({
    role_prompt: "file",
    action_hint: "file",
  });

  const [newStyleId, setNewStyleId] = useState("");
  const [newStyleLabel, setNewStyleLabel] = useState("");
  const [newStyleVideoModes, setNewStyleVideoModes] = useState<StyleVideoGenMode[]>([]);

  const [newAgentId, setNewAgentId] = useState("");
  const [newAgentLabel, setNewAgentLabel] = useState("");
  const [newAgentBasedOn, setNewAgentBasedOn] = useState<string>(CLONABLE_AGENT_TEMPLATES[0]);
  const [showNewAgentModal, setShowNewAgentModal] = useState(false);
  const [showToolPicker, setShowToolPicker] = useState(false);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [skillSearchQuery, setSkillSearchQuery] = useState("");
  const [inspectedTool, setInspectedTool] = useState<AgentToolOption | null>(null);
  const [toolSearchQuery, setToolSearchQuery] = useState("");
  const [newAgentModalTab, setNewAgentModalTab] = useState<"builtin" | "custom">("builtin");

  const toolPickerResize = useResizableDrawerWidth({
    storageKey: "svf.drawerWidth.toolPicker",
    defaultWidth: Math.min(
      780,
      typeof window !== "undefined" ? Math.round(window.innerWidth * 0.62) : 780,
    ),
    minWidth: inspectedTool ? 720 : 400,
    maxWidthRatio: inspectedTool ? 0.94 : 0.92,
  });

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const allStyleModes = useMemo(() => {
    return normalizeStyleModeOptions(styleModes?.style_modes ?? []);
  }, [styleModes]);

  /** Profile 下拉：API 列表与风格 1:1 对齐，未保存的自定义风格也可见。 */
  const profileOptions = useMemo(() => {
    const byId = new Map((config?.available_profiles ?? []).map((p) => [p.id, p]));
    for (const style of allStyleModes) {
      if (byId.has(style.id)) continue;
      byId.set(style.id, {
        id: style.id,
        label: style.label,
        builtin: style.builtin,
        deletable: !style.builtin,
        editable: style.id !== "default",
        restorable: style.builtin && BUILTIN_STYLE_TEMPLATES.includes(style.id as (typeof BUILTIN_STYLE_TEMPLATES)[number]),
      });
    }
    const ordered: PromptProfileOption[] = [];
    const defaultProfile = byId.get("default");
    if (defaultProfile) {
      ordered.push(defaultProfile);
      byId.delete("default");
    }
    for (const id of BUILTIN_STYLE_TEMPLATES) {
      const p = byId.get(id);
      if (p) {
        ordered.push(p);
        byId.delete(id);
      }
    }
    ordered.push(...Array.from(byId.values()).sort((a, b) => a.label.localeCompare(b.label)));
    return ordered;
  }, [config?.available_profiles, allStyleModes]);

  const stats = useMemo(
    () => ({
      agents: config?.agents.length ?? 0,
      styles: allStyleModes.length,
    }),
    [config, allStyleModes.length],
  );

  useEffect(() => {
    if (!config) return;
    setProfiles({ ...config.prompt_profiles });
    setCustomProfiles([...config.custom_profiles]);
    setCustomStyles(
      config.style_modes.filter(
        (s) => !s.builtin && !REMOVED_STYLE_MODE_IDS.has(s.id),
      ),
    );
    setCustomAgents([...config.custom_agents]);
    setProfileAgents({ ...config.profile_agents });
    setPromptContent(JSON.parse(JSON.stringify(config.prompt_content)));
    setToolOverridesByProfile(JSON.parse(JSON.stringify(config.tool_overrides_by_profile ?? {})));
    setSkillAllowlistsByProfile(
      JSON.parse(JSON.stringify(config.skill_allowlists_by_profile ?? {})),
    );
    setSelectedProfile((current) => {
      if (current) return current;
      const preferred = config.available_profiles.find((p) => p.editable !== false);
      return preferred?.id ?? config.available_profiles[0]?.id ?? "";
    });
  }, [config]);

  /** 加载全部 Skill（含用户导入），供 Agent 勾选。 */
  const loadSkillCatalog = useCallback(async () => {
    const r = await fetch(`${API}/skills`);
    if (!r.ok) return;
    const list = (await r.json()) as SkillMetaItem[];
    setSkillCatalog(Array.isArray(list) ? list : []);
  }, []);

  useEffect(() => {
    void loadSkillCatalog();
  }, [loadSkillCatalog]);

  useEffect(() => {
    if (!selectedProfile) {
      setAgentsForProfile([]);
      setSelectedAgent("");
      return;
    }
    let cancelled = false;
    void fetchAgentsForProfile(selectedProfile)
      .then((agents) => {
        if (cancelled) return;
        setAgentsForProfile(agents);
        setSelectedAgent((current) =>
          current && agents.some((a) => a.name === current) ? current : agents[0]?.name ?? "",
        );
      })
      .catch(() => {
        if (!cancelled) setAgentsForProfile([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedProfile, fetchAgentsForProfile]);

  /** 按本地 roster 排序/过滤侧栏 Agent（未保存的增删即时生效）。 */
  const rosterAgentIds = useMemo(() => {
    const roster = profileAgents[selectedProfile];
    if (roster?.length) return roster;
    return agentsForProfile.map((a) => a.name);
  }, [profileAgents, selectedProfile, agentsForProfile]);

  const rosterAgents = useMemo(() => {
    const byName = Object.fromEntries(agentsForProfile.map((a) => [a.name, a]));
    return rosterAgentIds
      .map((id) => byName[id])
      .filter((a): a is AgentInfo => Boolean(a));
  }, [rosterAgentIds, agentsForProfile]);

  const loadPromptEditor = useCallback(
    async (agent: string, profile: string) => {
      if (!agent || !profile) return;
      try {
        const data = await fetchPrompt(agent, profile);
        const override = promptContent[agent]?.[profile];
        setRoleDraft(override?.role_prompt ?? data.role_prompt);
        setHintDraft(override?.action_hint ?? data.action_hint ?? "");
        setPromptSource(data.source);
      } catch {
        const agentInfo = agentsForProfile.find((a) => a.name === agent);
        setRoleDraft(agentInfo?.effective_role_prompt ?? "");
        setHintDraft(agentInfo?.action_hint ?? "");
      }
    },
    [agentsForProfile, fetchPrompt, promptContent],
  );

  useEffect(() => {
    if (!selectedAgent || !selectedProfile) return;
    void loadPromptEditor(selectedAgent, selectedProfile);
  }, [selectedAgent, selectedProfile, loadPromptEditor]);

  const selectedAgentInfo = rosterAgents.find((a) => a.name === selectedAgent);
  const selectedVisual = agentVisual(selectedAgentInfo?.based_on ?? selectedAgent);
  const selectedProfileMeta = profileOptions.find((p) => p.id === selectedProfile);
  const profileReadOnly = selectedProfileMeta?.editable === false;
  const profileRestorable = selectedProfileMeta?.restorable === true;

  const masterAgent = useMemo(
    () => rosterAgents.find((a) => a.name === MASTER_AGENT_ID) ?? null,
    [rosterAgents],
  );
  const subAgents = useMemo(
    () => rosterAgents.filter((a) => a.name !== MASTER_AGENT_ID),
    [rosterAgents],
  );
  const isMasterSelected = selectedAgent === MASTER_AGENT_ID;

  useEffect(() => {
    if (!showNewAgentModal) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeNewAgentModal();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showNewAgentModal]);

  function patchPromptContent(agent: string, profile: string, patch: AgentPromptContentOverride) {
    if (profile === "default") return;
    setPromptContent((prev) => ({
      ...prev,
      [agent]: {
        ...(prev[agent] ?? {}),
        [profile]: { ...(prev[agent]?.[profile] ?? {}), ...patch },
      },
    }));
  }

  function handleRoleChange(value: string) {
    setRoleDraft(value);
    patchPromptContent(selectedAgent, selectedProfile, { role_prompt: value });
  }

  function handleHintChange(value: string) {
    setHintDraft(value);
    patchPromptContent(selectedAgent, selectedProfile, { action_hint: value });
  }

  async function handleRestoreBuiltinProfile() {
    if (!profileRestorable || !selectedProfile) return;
    setSaving(true);
    setSaveMsg(null);
    setSaveError(null);
    try {
      await restoreBuiltinProfile(selectedProfile);
      setSaveMsg(t("agent.workbench.restoredProfile", { ns: "settings" }));
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleRestoreAllBuiltinProfiles() {
    setSaving(true);
    setSaveMsg(null);
    setSaveError(null);
    try {
      await restoreAllBuiltinProfiles();
      setSaveMsg(t("agent.workbench.restoredAllBuiltin", { ns: "settings" }));
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    setSaveError(null);
    try {
      const patch: AgentConfigPatch = {
        prompt_profiles: profiles,
        custom_profiles: customProfiles,
        style_modes: customStyles,
        prompt_content: promptContent,
        custom_agents: customAgents,
        profile_agents: profileAgents,
        tool_overrides_by_profile: toolOverridesByProfile,
        skill_allowlists_by_profile: skillAllowlistsByProfile,
      };
      await update(patch);
      setSaveMsg(t("agent.workbench.saved", { ns: "settings" }));
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  /** 切换新建风格表单中的 AI 生视频子模式。 */
  function toggleNewStyleVideoMode(mode: StyleVideoGenMode) {
    setNewStyleVideoModes((current) =>
      current.includes(mode) ? current.filter((m) => m !== mode) : [...current, mode],
    );
  }

  /** 更新已有自定义风格的 AI 生视频子模式列表。 */
  function updateCustomStyleVideo(id: string, video: StyleVideoGenMode[]) {
    setCustomStyles((list) =>
      list.map((style) =>
        style.id === id
          ? {
              ...style,
              video: video.length > 0 ? video : undefined,
              include_video_gen: video.length > 0,
            }
          : style,
      ),
    );
  }

  /** 切换已有自定义风格的一项 AI 生视频子模式。 */
  function toggleCustomStyleVideoMode(id: string, mode: StyleVideoGenMode) {
    const style = customStyles.find((s) => s.id === id);
    if (!style) return;
    const current = style.video ?? [];
    const next = current.includes(mode)
      ? current.filter((m) => m !== mode)
      : [...current, mode];
    updateCustomStyleVideo(id, next);
  }

  /** 翻译 AI 生视频子模式标签。 */
  function translateVideoGenMode(mode: StyleVideoGenMode) {
    return t(`shot.genMode.${mode}`, { ns: "board", defaultValue: mode });
  }

  /** 新增自定义视频风格（id + 显示名 + 可选 video 子模式），并同步创建同名 PromptProfile。 */
  function addCustomStyle() {
    const id = newStyleId.trim();
    if (!id) return;
    const label = newStyleLabel.trim() || id;
    const video = newStyleVideoModes.length > 0 ? [...newStyleVideoModes] : undefined;
    setCustomStyles((list) => [
      ...list.filter((s) => s.id !== id),
      {
        id,
        label,
        default_prompt_profile: id,
        include_video_gen: Boolean(video?.length),
        video,
        builtin: false,
      },
    ]);
    setCustomProfiles((list) => [
      ...list.filter((p) => p.id !== id),
      { id, label, based_on: "storybook" },
    ]);
    setProfileAgents((prev) => ({
      ...prev,
      [id]: prev[id] ?? [MASTER_AGENT_ID, ...CLONABLE_AGENT_TEMPLATES],
    }));
    setNewStyleId("");
    setNewStyleLabel("");
    setNewStyleVideoModes([]);
  }

  /** 删除自定义视频风格及关联 PromptProfile 与各 Agent 配置。 */
  function removeCustomStyle(id: string) {
    const removedProfile = customProfiles.find((p) => p.id === id);
    const fallback = removedProfile?.based_on ?? "default";

    setCustomStyles((list) => list.filter((s) => s.id !== id));
    setCustomProfiles((list) => list.filter((p) => p.id !== id));

    setPromptContent((prev) => {
      const next: typeof prev = {};
      for (const [agent, profiles] of Object.entries(prev)) {
        if (!(id in profiles)) {
          next[agent] = profiles;
          continue;
        }
        const agentMap = { ...profiles };
        delete agentMap[id];
        if (Object.keys(agentMap).length > 0) next[agent] = agentMap;
      }
      return next;
    });

    setProfiles((prev) => {
      const next = { ...prev };
      for (const [agent, profileId] of Object.entries(next)) {
        if (profileId === id) next[agent] = fallback;
      }
      return next;
    });

    setProfileAgents((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    setToolOverridesByProfile((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });

    if (selectedProfile === id) {
      setSelectedProfile(fallback);
    }
  }

  /** 关闭新建 Agent 弹窗并重置表单。 */
  function closeNewAgentModal() {
    setShowNewAgentModal(false);
    setNewAgentModalTab("builtin");
    setNewAgentId("");
    setNewAgentLabel("");
    setNewAgentBasedOn(CLONABLE_AGENT_TEMPLATES[0]);
  }

  /** 在当前 Profile 下新增自定义 Agent。 */
  function addCustomAgent() {
    if (!selectedProfile || profileReadOnly) return false;
    const id = newAgentId.trim();
    if (!id) return false;
    const label = newAgentLabel.trim() || id;
    setCustomAgents((list) => [
      ...list.filter((a) => a.id !== id),
      { id, label, based_on: newAgentBasedOn },
    ]);
    setProfileAgents((prev) => ({
      ...prev,
      [selectedProfile]: [...(prev[selectedProfile] ?? rosterAgentIds).filter((x) => x !== id), id],
    }));
    setSelectedAgent(id);
    return true;
  }

  /** 弹窗确认创建子 Agent。 */
  function handleCreateAgentFromModal() {
    if (addCustomAgent()) closeNewAgentModal();
  }

  function getToolOverride(agentName: string): AgentToolOverride {
    return toolOverridesByProfile[selectedProfile]?.[agentName] ?? {};
  }

  /** 当前 Agent 已显式配置的 Skill 白名单；undefined 表示尚未配置（视为全选）。 */
  function getConfiguredSkillAllowlist(agentName: string): string[] | undefined {
    const byAgent = skillAllowlistsByProfile[selectedProfile];
    if (!byAgent || !(agentName in byAgent)) return undefined;
    return byAgent[agentName] ?? [];
  }

  /** 当前 Agent 勾选态：未配置时默认全选目录中的 Skill。 */
  function getSelectedSkillIds(agentName: string): string[] {
    const configured = getConfiguredSkillAllowlist(agentName);
    if (configured === undefined) {
      return skillCatalog.map((s) => s.id);
    }
    return configured;
  }

  /** 写入某 Agent 的 Skill 白名单。 */
  function setSkillAllowlist(agentName: string, skillIds: string[]) {
    if (!selectedProfile || profileReadOnly) return;
    setSkillAllowlistsByProfile((prev) => {
      const profileMap = { ...(prev[selectedProfile] ?? {}) };
      profileMap[agentName] = [...skillIds];
      return { ...prev, [selectedProfile]: profileMap };
    });
  }

  /** 确保使用显式 Skill 白名单（从默认「全部」切入增删模式）。 */
  function ensureSkillAllowlist(agentName: string): string[] {
    const configured = getConfiguredSkillAllowlist(agentName);
    if (configured !== undefined) return [...configured];
    return skillCatalog.map((s) => s.id);
  }

  /** 从已关联 Skill 中移除一项。 */
  function removeSelectedSkill(agentName: string, skillId: string) {
    const next = ensureSkillAllowlist(agentName).filter((id) => id !== skillId);
    setSkillAllowlist(agentName, next);
  }

  /** 向已关联 Skill 中添加一项。 */
  function addSelectedSkill(agentName: string, skillId: string) {
    const next = new Set(ensureSkillAllowlist(agentName));
    next.add(skillId);
    setSkillAllowlist(agentName, [...next]);
  }

  /** 可添加到当前 Agent 的 Skill（排除已选，支持搜索）。 */
  const addableSkills = useMemo(() => {
    if (!selectedAgent) return [] as SkillMetaItem[];
    const selected = new Set(getSelectedSkillIds(selectedAgent));
    const q = skillSearchQuery.trim().toLowerCase();
    return skillCatalog.filter((skill) => {
      if (selected.has(skill.id)) return false;
      if (!q) return true;
      return (
        skill.id.toLowerCase().includes(q) ||
        (skill.title || "").toLowerCase().includes(q) ||
        (skill.description || "").toLowerCase().includes(q) ||
        (skill.aliases || []).some((a) => a.toLowerCase().includes(q))
      );
    });
  }, [skillCatalog, selectedAgent, skillSearchQuery, skillAllowlistsByProfile, selectedProfile]);

  /** 关闭 Skill 选择抽屉。 */
  function closeSkillPicker() {
    setShowSkillPicker(false);
    setSkillSearchQuery("");
  }

  /** Esc 关闭 Skill 选择抽屉。 */
  useEffect(() => {
    if (!showSkillPicker) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeSkillPicker();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showSkillPicker]);

  /** 渲染当前 Agent 的 Skill 关联（与工具区相同的增删列表 + 抽屉）。 */
  function renderSkillSection(agentName: string) {
    const selectedIds = getSelectedSkillIds(agentName);
    const selectedSkills = selectedIds
      .map((id) => skillCatalog.find((s) => s.id === id))
      .filter((s): s is SkillMetaItem => Boolean(s));
    return (
      <div className="aw-tools-manage aw-skills-manage">
        {!profileReadOnly && (
          <div className="aw-tools-manage-head">
            <button
              type="button"
              className="aw-btn-add aw-btn-add-compact"
              onClick={() => {
                setSkillSearchQuery("");
                setShowSkillPicker(true);
              }}
            >
              + {t("agent.workbench.addSkill", { ns: "settings" })}
            </button>
            {onOpenSkills && (
              <button type="button" className="aw-btn-ghost aw-btn-add-compact" onClick={onOpenSkills}>
                {t("agent.workbench.openSkillLibrary", { ns: "settings" })}
              </button>
            )}
          </div>
        )}
        {selectedSkills.length === 0 ? (
          <p className="aw-tools-empty">
            {skillCatalog.length === 0
              ? t("agent.workbench.skillsEmpty", { ns: "settings" })
              : t("agent.workbench.skillsNoneLinked", { ns: "settings" })}
            {skillCatalog.length === 0 && onOpenSkills ? (
              <>
                {" "}
                <button type="button" className="aw-text-link" onClick={onOpenSkills}>
                  {t("agent.workbench.openSkillLibrary", { ns: "settings" })}
                </button>
              </>
            ) : null}
          </p>
        ) : (
          <div className="aw-tools-list-scroll">
            <ul className="aw-tools-list aw-skill-linked-list">
              {selectedSkills.map((skill) => (
                <li key={skill.id} className="aw-tool-row aw-skill-linked-row">
                  <div className="aw-skill-linked-sprocket" aria-hidden />
                  <div className="aw-tool-row-main">
                    <div className="aw-tool-main">
                      <span className="aw-tool-name">{skill.title || skill.id}</span>
                      <span className="aw-skill-slash">/{skill.id}</span>
                      {skill.source ? (
                        <span className={`aw-skill-source aw-skill-source-${skill.source}`}>
                          {skill.source}
                        </span>
                      ) : null}
                    </div>
                    {skill.description ? (
                      <p className="aw-skill-purpose">{skill.description}</p>
                    ) : null}
                    {skill.highlights && skill.highlights.length > 0 ? (
                      <ul className="aw-skill-highlights">
                        {skill.highlights.map((h) => (
                          <li key={h}>{h}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  {!profileReadOnly && (
                    <button
                      type="button"
                      className="aw-btn-ghost aw-tool-remove"
                      onClick={() => removeSelectedSkill(agentName, skill.id)}
                      aria-label={t("agent.workbench.removeSkill", { ns: "settings" })}
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  /** 当前 Agent 已选中的非 system 工具 action 列表。 */
  function getSelectedToolActions(agent: AgentInfo): string[] {
    const ov = getToolOverride(agent.name);
    if (ov.include_only?.length) return ov.include_only;
    return (agent.tool_options ?? []).map((t) => t.action || t.name);
  }

  /** 确保 override 使用 include_only 白名单模式。 */
  function ensureIncludeOnly(agent: AgentInfo): string[] {
    const ov = getToolOverride(agent.name);
    if (ov.include_only?.length) return [...ov.include_only];
    return getSelectedToolActions(agent);
  }

  /** 写入 include_only 并清除 exclude。 */
  function setIncludeOnly(agentName: string, tools: string[]) {
    if (!selectedProfile || profileReadOnly) return;
    setToolOverridesByProfile((prev) => {
      const profileMap = { ...(prev[selectedProfile] ?? {}) };
      profileMap[agentName] = { include_only: tools };
      return { ...prev, [selectedProfile]: profileMap };
    });
  }

  /** 从已选工具中移除一项。 */
  function removeSelectedTool(agent: AgentInfo, action: string) {
    const next = ensureIncludeOnly(agent).filter((t) => t !== action);
    setIncludeOnly(agent.name, next);
  }

  /** 向已选工具中添加一项（可跨 Agent）。 */
  function addSelectedTool(agent: AgentInfo, action: string) {
    const next = new Set(ensureIncludeOnly(agent));
    next.add(action);
    setIncludeOnly(agent.name, [...next]);
  }

  /** 扁平化全局非 system 工具目录。 */
  const globalToolCatalog = useMemo(() => {
    const source = toolsCatalog?.catalog?.length
      ? toolsCatalog.catalog
      : Object.values(toolsCatalog?.agents ?? {}).flat();
    if (!source.length) return [] as NonNullable<AgentInfo["tool_options"]>;
    const seen = new Set<string>();
    const out: NonNullable<AgentInfo["tool_options"]> = [];
    for (const item of source) {
      if (item.kind === "system" || seen.has(item.action)) continue;
      seen.add(item.action);
      out.push({
        name: item.name,
        action: item.action,
        description: item.description,
        kind: item.kind,
        read_only: item.read_only,
        scopes: item.scopes,
        operations: item.operations,
        asset_layer: item.asset_layer,
        affected_data_read: item.affected_data_read,
        affected_data_write: item.affected_data_write,
        boundary_note: item.boundary_note,
        may_write_edit_timeline: item.may_write_edit_timeline,
        multi_scope_read: item.multi_scope_read,
        agent: item.agent,
        input_schema: item.input_schema,
        output_schema: item.output_schema,
      });
    }
    return out.sort((a, b) => a.action.localeCompare(b.action));
  }, [toolsCatalog]);

  /** 可添加到当前 Agent 的全局工具（排除已选）。 */
  const addableTools = useMemo(() => {
    if (!selectedAgentInfo) return [] as AgentToolOption[];
    const selected = new Set(getSelectedToolActions(selectedAgentInfo));
    const q = toolSearchQuery.trim().toLowerCase();
    return globalToolCatalog.filter((tool) => {
      if (selected.has(tool.action)) return false;
      if (!q) return true;
      return (
        tool.action.toLowerCase().includes(q) ||
        tool.description.toLowerCase().includes(q) ||
        tool.name.toLowerCase().includes(q)
      );
    });
  }, [globalToolCatalog, selectedAgentInfo, toolSearchQuery, toolOverridesByProfile]);

  /** 可添加工具目录布局（跨范围读取置顶）。 */
  const addableToolLayout = useMemo(
    () => layoutAgentToolCatalog(addableTools),
    [addableTools],
  );

  /** 关闭工具选择抽屉并重置详情侧栏。 */
  function closeToolPicker() {
    setShowToolPicker(false);
    setInspectedTool(null);
  }

  /** Esc 关闭工具选择抽屉。 */
  useEffect(() => {
    if (!showToolPicker) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeToolPicker();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showToolPicker]);

  /** 当前 Profile 可添加的内置子 Agent。 */
  const availableBuiltinAgents = useMemo(() => {
    const inRoster = new Set(rosterAgentIds);
    return CLONABLE_AGENT_TEMPLATES.filter((id) => !inRoster.has(id));
  }, [rosterAgentIds]);

  /** 将内置 Agent 加入当前 Profile roster。 */
  function addBuiltinAgentToProfile(agentId: string) {
    if (!selectedProfile || profileReadOnly) return;
    setProfileAgents((prev) => ({
      ...prev,
      [selectedProfile]: [...(prev[selectedProfile] ?? rosterAgentIds), agentId],
    }));
    setSelectedAgent(agentId);
  }

  /** 从 Profile roster 移除 Agent（主编排不可删；custom 无引用时清理定义）。 */
  function removeAgentFromProfile(agentId: string) {
    if (agentId === MASTER_AGENT_ID || !selectedProfile || profileReadOnly) return;
    const nextProfileAgents = {
      ...profileAgents,
      [selectedProfile]: (profileAgents[selectedProfile] ?? rosterAgentIds).filter((x) => x !== agentId),
    };
    setProfileAgents(nextProfileAgents);
    const isCustom = customAgents.some((a) => a.id === agentId);
    if (isCustom) {
      const stillUsed = Object.values(nextProfileAgents).some((ids) => ids.includes(agentId));
      if (!stillUsed) {
        setCustomAgents((list) => list.filter((a) => a.id !== agentId));
        setPromptContent((prev) => {
          const next = { ...prev };
          delete next[agentId];
          return next;
        });
      }
    }
    setToolOverridesByProfile((prev) => {
      const profileMap = { ...(prev[selectedProfile] ?? {}) };
      delete profileMap[agentId];
      return { ...prev, [selectedProfile]: profileMap };
    });
    if (selectedAgent === agentId) {
      setSelectedAgent(MASTER_AGENT_ID);
    }
  }

  /** 翻译工具作用范围标签。 */
  function translateToolScope(scope: string) {
    return t(`agent.workbench.toolScopes.${scope}`, { ns: "settings", defaultValue: scope });
  }

  /** 翻译工具操作意义标签。 */
  function translateToolOperation(operation: string) {
    return t(`agent.workbench.toolOperations.${operation}`, { ns: "settings", defaultValue: operation });
  }

  /** 渲染跨范围读取工具的查询数据范围说明。 */
  function renderToolQueryRange(tool: AgentToolOption) {
    const reads = tool.affected_data_read ?? [];
    if (reads.length === 0) return null;
    return (
      <span className="aw-tool-query-range" title={reads.join("、")}>
        {t("agent.workbench.toolQueryRange", { ns: "settings" })}：{reads.join("、")}
      </span>
    );
  }

  /** 渲染单条工具元信息行。 */
  function renderToolRowContent(tool: AgentToolOption) {
    return (
      <>
        <span className="aw-tool-name">{tool.name}</span>
        {tool.description && tool.description !== tool.name && (
          <span className="aw-tool-desc">{tool.description}</span>
        )}
        {tool.multi_scope_read || (tool.affected_data_read?.length ?? 0) >= 2
          ? renderToolQueryRange(tool)
          : null}
        {renderToolTaxonomy(tool)}
      </>
    );
  }

  /** 渲染工具行右侧「详情」按钮。 */
  function renderToolInspectButton(tool: AgentToolOption, onInspect?: (tool: AgentToolOption) => void) {
    if (!onInspect) return null;
    return (
      <button
        type="button"
        className="aw-btn-ghost aw-tool-detail-btn"
        onClick={() => onInspect(tool)}
        aria-label={t("agent.workbench.toolDetailFor", {
          ns: "settings",
          action: tool.action,
        })}
      >
        {t("agent.workbench.toolDetail", { ns: "settings" })}
      </button>
    );
  }

  /** 渲染可添加/已选工具行（主区 + 详情 + 可选删除）。 */
  function renderToolActionRow(
    tool: AgentToolOption,
    options: {
      onPick?: (action: string) => void;
      onInspect?: (tool: AgentToolOption) => void;
      onRemove?: (action: string) => void;
      rowClassName?: string;
    },
  ) {
    const { onPick, onInspect, onRemove, rowClassName } = options;
    return (
      <li key={tool.action} className={rowClassName ? `aw-tool-pick-row ${rowClassName}` : "aw-tool-pick-row"}>
        {onPick ? (
          <button type="button" className="aw-tool-pick-btn" onClick={() => onPick(tool.action)}>
            <span className="aw-tool-row-main">{renderToolRowContent(tool)}</span>
          </button>
        ) : (
          <div className="aw-tool-row-main aw-tool-row-main-static">{renderToolRowContent(tool)}</div>
        )}
        {renderToolInspectButton(tool, onInspect)}
        {onRemove && (
          <button
            type="button"
            className="aw-btn-ghost aw-tool-remove"
            onClick={() => onRemove(tool.action)}
            aria-label={t("agent.workbench.removeTool", { ns: "settings" })}
          >
            ×
          </button>
        )}
      </li>
    );
  }

  /** 渲染跨范围读取工具分区。 */
  function renderMultiScopeReadSection(
    tools: AgentToolOption[],
    onPick?: (action: string) => void,
    onRemove?: (action: string) => void,
    onInspect?: (tool: AgentToolOption) => void,
  ) {
    if (tools.length === 0) return null;
    return (
      <section className="aw-tool-scope-group aw-tool-multi-scope-group">
        <header className="aw-tool-scope-head aw-tool-multi-scope-head">
          <span className="aw-tool-scope-eyebrow">{t("agent.workbench.toolGroupMultiScopeRead", { ns: "settings" })}</span>
          <h4 className="aw-tool-scope-title">{t("agent.workbench.toolGroupMultiScopeReadTitle", { ns: "settings" })}</h4>
          <p className="aw-tool-multi-scope-hint">{t("agent.workbench.toolGroupMultiScopeReadHint", { ns: "settings" })}</p>
        </header>
        <ul className={`aw-tools-pick-list aw-tools-pick-list-compact${onRemove ? " aw-tools-list" : ""}`}>
          {tools.map((tool) =>
            renderToolActionRow(tool, {
              onPick,
              onInspect,
              onRemove,
              rowClassName: onRemove ? "aw-tool-row" : undefined,
            }),
          )}
        </ul>
      </section>
    );
  }

  /** 渲染按作用范围与操作意义分组的工具目录。 */
  function renderScopedToolGroups(
    groups: ReturnType<typeof layoutAgentToolCatalog>["byScope"],
    onPick?: (action: string) => void,
    onInspect?: (tool: AgentToolOption) => void,
  ) {
    return groups.map((scopeGroup) => (
      <section key={scopeGroup.scope} className="aw-tool-scope-group">
        <header className="aw-tool-scope-head">
          <span className="aw-tool-scope-eyebrow">{t("agent.workbench.toolGroupScope", { ns: "settings" })}</span>
          <h4 className="aw-tool-scope-title">{translateToolScope(scopeGroup.scope)}</h4>
          <span className="aw-tool-scope-code">{scopeGroup.scope}</span>
        </header>
        {scopeGroup.operations.map((operationGroup) => (
          <div key={`${scopeGroup.scope}-${operationGroup.operation}`} className="aw-tool-operation-group">
            <div className="aw-tool-operation-head">
              <span className="aw-tool-operation-label">{t("agent.workbench.toolGroupOperation", { ns: "settings" })}</span>
              <span className="aw-badge aw-tool-operation-tag">{translateToolOperation(operationGroup.operation)}</span>
              <span className="aw-tool-operation-count">{operationGroup.tools.length}</span>
            </div>
            <ul className="aw-tools-pick-list aw-tools-pick-list-compact">
              {operationGroup.tools.map((tool) =>
                renderToolActionRow(tool, {
                  onPick,
                  onInspect,
                }),
              )}
            </ul>
          </div>
        ))}
      </section>
    ));
  }

  /** 渲染完整工具目录（跨范围读取 + 单范围分组）。 */
  function renderGroupedToolCatalog(
    layout: ReturnType<typeof layoutAgentToolCatalog>,
    onPick?: (action: string) => void,
    emptyLabel?: string,
    onInspect?: (tool: AgentToolOption) => void,
  ) {
    if (layout.multiScopeRead.length === 0 && layout.byScope.length === 0) {
      return <p className="aw-tools-empty">{emptyLabel}</p>;
    }
    return (
      <div className="aw-tools-catalog">
        {renderMultiScopeReadSection(layout.multiScopeRead, onPick, undefined, onInspect)}
        {renderScopedToolGroups(layout.byScope, onPick, onInspect)}
      </div>
    );
  }

  /** 渲染作用范围 / 操作意义标签。 */
  function renderToolTaxonomy(tool: {
    scopes?: string[];
    operations?: string[];
    asset_layer?: string;
    affected_data_read?: string[];
    affected_data_write?: string[];
    boundary_note?: string;
    multi_scope_read?: boolean;
  }) {
    const scopes = tool.scopes ?? [];
    const operations = tool.operations ?? [];
    const writes = tool.affected_data_write ?? [];
    const reads = tool.affected_data_read ?? [];
    if (
      scopes.length === 0 &&
      operations.length === 0 &&
      writes.length === 0 &&
      reads.length === 0 &&
      !tool.asset_layer
    ) {
      return null;
    }
    return (
      <span className="aw-tool-taxonomy">
        {tool.asset_layer && (
          <span className="aw-badge aw-tool-layer" title={tool.boundary_note || tool.asset_layer}>
            {tool.asset_layer}
          </span>
        )}
        {scopes.map((scope) => (
          <span key={`s-${scope}`} className="aw-badge aw-tool-scope" title={t(`agent.workbench.toolScopes.${scope}`, { ns: "settings", defaultValue: scope })}>
            {t(`agent.workbench.toolScopes.${scope}`, { ns: "settings", defaultValue: scope })}
          </span>
        ))}
        {operations.map((op) => (
          <span key={`o-${op}`} className="aw-badge aw-tool-operation" title={t(`agent.workbench.toolOperations.${op}`, { ns: "settings", defaultValue: op })}>
            {t(`agent.workbench.toolOperations.${op}`, { ns: "settings", defaultValue: op })}
          </span>
        ))}
        {writes.length > 0 && (
          <span className="aw-badge aw-tool-write" title={writes.join("、")}>
            写：{writes.join("、")}
          </span>
        )}
        {writes.length === 0 && reads.length > 0 && !tool.multi_scope_read && (
          <span className="aw-badge aw-tool-read" title={reads.join("、")}>
            读：{reads.join("、")}
          </span>
        )}
      </span>
    );
  }

  /** 解析已选工具的展示元数据。 */
  function resolveToolMeta(agent: AgentInfo, action: string) {
    const fromAgent = agent.tool_options?.find((t) => (t.action || t.name) === action);
    if (fromAgent) return fromAgent;
    return globalToolCatalog.find((t) => t.action === action) ?? {
      name: action,
      action,
      description: action,
      read_only: false,
    };
  }

  /** 渲染已选工具列表（增删模式，按作用范围与操作意义分组）。 */
  function renderToolSection(agent: AgentInfo) {
    const selected = getSelectedToolActions(agent);
    const selectedTools = selected.map((action) => resolveToolMeta(agent, action));
    const selectedLayout = layoutAgentToolCatalog(selectedTools);

    return (
      <div className="aw-tools-manage">
        {!profileReadOnly && (
          <div className="aw-tools-manage-head">
            <button
              type="button"
              className="aw-btn-add aw-btn-add-compact"
              onClick={() => {
                setToolSearchQuery("");
                setInspectedTool(null);
                setShowToolPicker(true);
              }}
            >
              + {t("agent.workbench.addTool", { ns: "settings" })}
            </button>
          </div>
        )}
        {selected.length === 0 ? (
          <p className="aw-tools-empty">{t("agent.workbench.toolsEmpty", { ns: "settings" })}</p>
        ) : (
          <div className="aw-tools-list-scroll">
            {renderMultiScopeReadSection(
              selectedLayout.multiScopeRead,
              undefined,
              profileReadOnly ? undefined : (action) => removeSelectedTool(agent, action),
            )}
            {selectedLayout.byScope.map((scopeGroup) => (
              <section key={scopeGroup.scope} className="aw-tool-scope-group aw-tool-scope-group-inline">
                <header className="aw-tool-scope-head">
                  <span className="aw-tool-scope-eyebrow">{t("agent.workbench.toolGroupScope", { ns: "settings" })}</span>
                  <h4 className="aw-tool-scope-title">{translateToolScope(scopeGroup.scope)}</h4>
                </header>
                {scopeGroup.operations.map((operationGroup) => (
                  <div key={`${scopeGroup.scope}-${operationGroup.operation}`} className="aw-tool-operation-group">
                    <div className="aw-tool-operation-head">
                      <span className="aw-tool-operation-label">{t("agent.workbench.toolGroupOperation", { ns: "settings" })}</span>
                      <span className="aw-badge aw-tool-operation-tag">{translateToolOperation(operationGroup.operation)}</span>
                    </div>
                    <ul className="aw-tools-list">
                      {operationGroup.tools.map((tool) => (
                        <li key={tool.action} className="aw-tool-row">
                          <div className="aw-tool-row-main">{renderToolRowContent(tool)}</div>
                          {!profileReadOnly && (
                            <button
                              type="button"
                              className="aw-btn-ghost aw-tool-remove"
                              onClick={() => removeSelectedTool(agent, tool.action)}
                              aria-label={t("agent.workbench.removeTool", { ns: "settings" })}
                            >
                              ×
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </section>
            ))}
          </div>
        )}
      </div>
    );
  }

  /** 渲染侧栏 Agent 选择按钮。 */
  function renderAgentButton(agent: AgentInfo, variant: "master" | "sub") {
    const vis = agentVisual(agent.based_on ?? agent.name);
    const canRemove = !profileReadOnly && agent.name !== MASTER_AGENT_ID;
    return (
      <div
        key={agent.name}
        className={`aw-agent-row${variant === "master" ? " aw-agent-row-master" : ""}`}
      >
        <button
          type="button"
          className={`aw-agent-btn${variant === "master" ? " aw-agent-btn-master" : ""}${
            selectedAgent === agent.name ? " active" : ""
          }`}
          style={{ ["--agent-accent" as string]: vis.accent }}
          onClick={() => setSelectedAgent(agent.name)}
        >
          <span className={`aw-agent-avatar${variant === "master" ? " aw-agent-avatar-master" : ""}`}>
            {vis.initials}
          </span>
          <span className="aw-agent-text">
            <span className="aw-agent-name">{agent.display_name}</span>
            <span className="aw-agent-id">
              {agent.name}
              {agent.based_on ? ` · ${agent.based_on}` : ""}
            </span>
          </span>
        </button>
        {canRemove && (
          <button
            type="button"
            className="aw-btn-ghost aw-agent-remove"
            onClick={() => removeAgentFromProfile(agent.name)}
            aria-label={t("agent.workbench.removeAgent", { ns: "settings" })}
          >
            ×
          </button>
        )}
      </div>
    );
  }

  /** 删除自定义 PromptProfile（default 不可删）。 */
  function removeCustomProfile(profileId: string) {
    const profile = config?.available_profiles.find((p) => p.id === profileId);
    if (!profile?.deletable) return;
    const removedProfile = customProfiles.find((p) => p.id === profileId);
    const fallback = removedProfile?.based_on ?? "default";

    setCustomProfiles((list) => list.filter((p) => p.id !== profileId));
    setCustomStyles((list) => list.filter((s) => s.default_prompt_profile !== profileId && s.id !== profileId));

    setPromptContent((prev) => {
      const next: typeof prev = {};
      for (const [agent, profiles] of Object.entries(prev)) {
        if (!(profileId in profiles)) {
          next[agent] = profiles;
          continue;
        }
        const agentMap = { ...profiles };
        delete agentMap[profileId];
        if (Object.keys(agentMap).length > 0) next[agent] = agentMap;
      }
      return next;
    });

    setProfiles((prev) => {
      const next = { ...prev };
      for (const [agent, pid] of Object.entries(next)) {
        if (pid === profileId) next[agent] = fallback;
      }
      return next;
    });

    setProfileAgents((prev) => {
      const next = { ...prev };
      delete next[profileId];
      return next;
    });
    setToolOverridesByProfile((prev) => {
      const next = { ...prev };
      delete next[profileId];
      return next;
    });
    setSkillAllowlistsByProfile((prev) => {
      const next = { ...prev };
      delete next[profileId];
      return next;
    });

    if (selectedProfile === profileId) {
      setSelectedProfile(fallback);
    }
  }

  return (
    <AppShell
      pageClass="settings-page"
      mainClass="settings-main agent-settings-main agent-workbench-page"
      className="settings-top-bar"
      title={t("agentConfig", { ns: "nav" })}
      lead={
        <button type="button" className="btn-secondary" onClick={onBack}>
          {t("backToChat", { ns: "nav" })}
        </button>
      }
      trail={
        <>
          <ThemeToggle />
          <LocaleSwitcher />
          {onOpenSkills && (
            <button type="button" className="btn-secondary btn-config" onClick={onOpenSkills}>
              {t("skillLibrary", { ns: "nav" })}
            </button>
          )}
        </>
      }
    >
      {loading && (
        <div className="aw-loading" role="status">
          <span className="aw-loading-pulse" aria-hidden />
          {t("actions.loading", { ns: "common" })}
        </div>
      )}

      {error && (
        <div className="settings-alert error">
          <p>{error}</p>
          <button type="button" onClick={refresh}>
            {t("actions.retry", { ns: "common" })}
          </button>
        </div>
      )}

      {!loading && config && (
        <form className="agent-workbench-form" onSubmit={handleSave}>
          <header className="aw-hero">
            <p className="aw-hero-eyebrow">{t("agent.workbench.eyebrow", { ns: "settings" })}</p>
            <h1 className="aw-hero-title">{t("agent.workbench.heroTitle", { ns: "settings" })}</h1>
            <p className="aw-hero-lead">{t("agent.workbench.intro", { ns: "settings" })}</p>
            <div className="aw-stats">
              <div className="aw-stat">
                <span className="aw-stat-value">{stats.agents}</span>
                <span className="aw-stat-label">{t("agent.workbench.statAgents", { ns: "settings" })}</span>
              </div>
              <div className="aw-stat">
                <span className="aw-stat-value">{stats.styles}</span>
                <span className="aw-stat-label">{t("agent.workbench.statStyles", { ns: "settings" })}</span>
              </div>
            </div>
          </header>

          <nav className="aw-tabs" role="tablist" aria-label={t("agent.workbench.tabNav", { ns: "settings" })}>
            {(
              [
                { id: "modes" as const, icon: "◈", label: t("agent.workbench.tabStyles", { ns: "settings" }) },
                { id: "agents" as const, icon: "⌁", label: t("agent.workbench.tabAgents", { ns: "settings" }) },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
                className={`aw-tab${activeTab === tab.id ? " active" : ""}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="aw-tab-icon" aria-hidden>
                  {tab.icon}
                </span>
                {tab.label}
              </button>
            ))}
          </nav>

          {activeTab === "modes" && (
            <section className="aw-panel" role="tabpanel">
              <div className="aw-panel-head">
                <div>
                  <h2 className="aw-panel-title">{t("agent.workbench.stylesTitle", { ns: "settings" })}</h2>
                  <p className="aw-panel-desc">{t("agent.workbench.stylesDesc", { ns: "settings" })}</p>
                </div>
                <button
                  type="button"
                  className="aw-btn-ghost"
                  disabled={saving}
                  onClick={() => void handleRestoreAllBuiltinProfiles()}
                >
                  {t("agent.workbench.restoreAllBuiltin", { ns: "settings" })}
                </button>
              </div>
              <div className="aw-card aw-card-full">
                <div className="aw-inline-form">
                  <input
                    placeholder="id"
                    value={newStyleId}
                    onChange={(e) => setNewStyleId(e.target.value)}
                    aria-label={t("agent.workbench.styleId", { ns: "settings" })}
                  />
                  <input
                    placeholder={t("agent.workbench.label", { ns: "settings" })}
                    value={newStyleLabel}
                    onChange={(e) => setNewStyleLabel(e.target.value)}
                    aria-label={t("agent.workbench.label", { ns: "settings" })}
                  />
                  <button type="button" className="aw-btn-add" onClick={addCustomStyle}>
                    + {t("agent.workbench.addStyle", { ns: "settings" })}
                  </button>
                </div>
                <fieldset className="aw-video-mode-group">
                  <legend>{t("agent.workbench.styleVideoModes", { ns: "settings" })}</legend>
                  <p className="aw-video-mode-hint">
                    {t("agent.workbench.styleVideoModesHint", { ns: "settings" })}
                  </p>
                  <div className="aw-video-mode-options">
                    {STYLE_VIDEO_OPTIONS.map((mode) => (
                      <label key={mode} className="aw-check-label">
                        <input
                          type="checkbox"
                          checked={newStyleVideoModes.includes(mode)}
                          onChange={() => toggleNewStyleVideoMode(mode)}
                        />
                        {translateVideoGenMode(mode)}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <ul className="aw-chip-list aw-chip-list-tall">
                  {allStyleModes.map((s) => (
                    <li key={s.id} className="aw-chip">
                      <span className="aw-chip-label">{s.label}</span>
                      <code>{s.id}</code>
                      {s.builtin && s.video?.length ? (
                        <span className="aw-badge video">
                          video: {s.video.map((mode) => translateVideoGenMode(mode)).join(" · ")}
                        </span>
                      ) : null}
                      {!s.builtin && (
                        <div className="aw-chip-video-modes" role="group" aria-label={t("agent.workbench.styleVideoModes", { ns: "settings" })}>
                          {STYLE_VIDEO_OPTIONS.map((mode) => (
                            <label key={mode} className="aw-check-label aw-check-label-compact">
                              <input
                                type="checkbox"
                                checked={(s.video ?? []).includes(mode)}
                                onChange={() => toggleCustomStyleVideoMode(s.id, mode)}
                              />
                              {translateVideoGenMode(mode)}
                            </label>
                          ))}
                        </div>
                      )}
                      <span className={`aw-badge ${s.builtin ? "builtin" : "custom"}`}>
                        {s.builtin ? "builtin" : "custom"}
                      </span>
                      {!s.builtin && (
                        <button
                          type="button"
                          className="aw-btn-ghost"
                          onClick={() => removeCustomStyle(s.id)}
                        >
                          {t("agent.workbench.remove", { ns: "settings" })}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          {activeTab === "agents" && (
            <section className="aw-panel" role="tabpanel">
              <div className="aw-panel-head aw-panel-head-split">
                <div>
                  <h2 className="aw-panel-title">{t("agent.workbench.agentEditTitle", { ns: "settings" })}</h2>
                  <p className="aw-panel-desc">{t("agent.workbench.agentEditDesc", { ns: "settings" })}</p>
                </div>
                <label className="aw-field aw-profile-picker">
                  {t("agent.workbench.selectProfile", { ns: "settings" })}
                  <div className="aw-profile-picker-row">
                    <select
                      value={selectedProfile}
                      onChange={(e) => setSelectedProfile(e.target.value)}
                    >
                      {profileOptions.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                    {profileRestorable && (
                      <button
                        type="button"
                        className="aw-btn-ghost"
                        disabled={saving}
                        onClick={() => void handleRestoreBuiltinProfile()}
                      >
                        {t("agent.workbench.restoreBuiltin", { ns: "settings" })}
                      </button>
                    )}
                    {selectedProfileMeta?.deletable && (
                      <button
                        type="button"
                        className="aw-btn-ghost"
                        onClick={() => removeCustomProfile(selectedProfile)}
                      >
                        {t("agent.workbench.removeProfile", { ns: "settings" })}
                      </button>
                    )}
                  </div>
                </label>
              </div>

              {!selectedProfile && (
                <p className="aw-empty-hint">{t("agent.workbench.selectProfileHint", { ns: "settings" })}</p>
              )}

              {selectedProfile && profileReadOnly && (
                <p className="aw-readonly-banner" role="status">
                  {t("agent.workbench.defaultReadOnly", { ns: "settings" })}
                </p>
              )}

              {selectedProfile && (
                <div className="aw-editor-shell">
                  <aside className="aw-agent-rail" aria-label={t("agent.workbench.agentRail", { ns: "settings" })}>
                    {masterAgent && (
                      <div className="aw-master-zone">
                        <p className="aw-rail-section-label">
                          {t("agent.workbench.masterSection", { ns: "settings" })}
                        </p>
                        {renderAgentButton(masterAgent, "master")}
                        <p className="aw-master-zone-hint">
                          {t("agent.workbench.masterHint", { ns: "settings" })}
                        </p>
                      </div>
                    )}

                    <div className="aw-sub-agents-zone">
                      <div className="aw-rail-section-head">
                        <p className="aw-rail-section-label">
                          {t("agent.workbench.subAgentsSection", { ns: "settings" })}
                        </p>
                        {!profileReadOnly && (
                          <button
                            type="button"
                            className="aw-btn-add aw-btn-add-compact"
                            onClick={() => setShowNewAgentModal(true)}
                          >
                            + {t("agent.workbench.addAgent", { ns: "settings" })}
                          </button>
                        )}
                      </div>
                      <div className="aw-sub-agents-list">
                        {subAgents.length === 0 ? (
                          <p className="aw-sub-agents-empty">
                            {t("agent.workbench.subAgentsEmpty", { ns: "settings" })}
                          </p>
                        ) : (
                          subAgents.map((agent) => renderAgentButton(agent, "sub"))
                        )}
                      </div>
                    </div>
                  </aside>

                  {selectedAgentInfo ? (
                    <div
                      className={`aw-editor-main${isMasterSelected ? " aw-editor-main-master" : ""}`}
                      style={{ ["--agent-accent" as string]: selectedVisual.accent }}
                    >
                      <div className="aw-toolbar">
                        <span className="aw-editing-badge">
                          {selectedProfileMeta?.label ?? selectedProfile}
                          {" · "}
                          {selectedAgentInfo.display_name}
                        </span>
                        {isMasterSelected && (
                          <span className="aw-badge aw-badge-master">
                            {t("agent.workbench.masterBadge", { ns: "settings" })}
                          </span>
                        )}
                      </div>
                      <div className="aw-viewfinder">
                        <div className="aw-field-block">
                          <div className="aw-field-head">
                            <span className="aw-field-name">role_prompt</span>
                            <span className={`aw-source-badge ${promptSource.role_prompt}`}>
                              {promptSource.role_prompt}
                            </span>
                          </div>
                          <textarea
                            className="aw-prompt-textarea role"
                            value={roleDraft}
                            readOnly={profileReadOnly}
                            disabled={profileReadOnly}
                            onChange={(e) => handleRoleChange(e.target.value)}
                            rows={10}
                            spellCheck={false}
                          />
                        </div>
                        {selectedAgent !== "super_video_master" && (
                          <div className="aw-field-block">
                            <div className="aw-field-head">
                              <span className="aw-field-name">action_hint</span>
                              <span className={`aw-source-badge ${promptSource.action_hint}`}>
                                {promptSource.action_hint}
                              </span>
                            </div>
                            <textarea
                              className="aw-prompt-textarea"
                              value={hintDraft}
                              readOnly={profileReadOnly}
                              disabled={profileReadOnly}
                              onChange={(e) => handleHintChange(e.target.value)}
                              rows={5}
                              spellCheck={false}
                            />
                          </div>
                        )}
                      </div>
                      <div className="aw-agent-tools-section">
                        <div className="aw-section-head">
                          <h3 className="aw-section-title">{t("agent.workbench.toolsSection", { ns: "settings" })}</h3>
                          <p className="aw-section-desc">{t("agent.workbench.toolsHint", { ns: "settings" })}</p>
                        </div>
                        {renderToolSection(selectedAgentInfo)}
                        <p className="aw-effective-bar">
                          <strong>effective</strong> {getSelectedToolActions(selectedAgentInfo).join(" · ")}
                        </p>
                      </div>
                      <div className="aw-agent-skills-section">
                        <div className="aw-section-head">
                          <h3 className="aw-section-title">{t("agent.workbench.skillsSection", { ns: "settings" })}</h3>
                          <p className="aw-section-desc">{t("agent.workbench.skillsHint", { ns: "settings" })}</p>
                        </div>
                        {renderSkillSection(selectedAgentInfo.name)}
                      </div>
                    </div>
                  ) : (
                    <p className="aw-empty-hint aw-editor-empty">
                      {t("agent.workbench.selectAgentHint", { ns: "settings" })}
                    </p>
                  )}
                </div>
              )}
            </section>
          )}

          {saveMsg && <div className="settings-alert success">{saveMsg}</div>}
          {saveError && <div className="settings-alert error">{saveError}</div>}

          <div className="aw-save-bar">
            <p className="aw-save-hint">{t("agent.workbench.saveHint", { ns: "settings" })}</p>
            <button type="submit" className="aw-save-btn" disabled={saving}>
              {saving
                ? t("actions.saving", { ns: "common" })
                : t("agent.saveProfile", { ns: "settings" })}
            </button>
          </div>
        </form>
      )}

      {showNewAgentModal && (
        <div
          className="aw-modal-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeNewAgentModal();
          }}
        >
          <div
            className="aw-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aw-new-agent-title"
          >
            <header className="aw-modal-head">
              <p className="aw-modal-eyebrow">{t("agent.workbench.subAgentsSection", { ns: "settings" })}</p>
              <h2 id="aw-new-agent-title" className="aw-modal-title">
                {t("agent.workbench.newAgentModalTitle", { ns: "settings" })}
              </h2>
              <p className="aw-modal-desc">{t("agent.workbench.newAgentModalDesc", { ns: "settings" })}</p>
              <div className="aw-modal-tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  className={newAgentModalTab === "builtin" ? "active" : ""}
                  onClick={() => setNewAgentModalTab("builtin")}
                >
                  {t("agent.workbench.addBuiltinAgent", { ns: "settings" })}
                </button>
                <button
                  type="button"
                  role="tab"
                  className={newAgentModalTab === "custom" ? "active" : ""}
                  onClick={() => setNewAgentModalTab("custom")}
                >
                  {t("agent.workbench.createCustomAgent", { ns: "settings" })}
                </button>
              </div>
            </header>
            <div className="aw-modal-body">
              {newAgentModalTab === "builtin" ? (
                <ul className="aw-builtin-agent-pick">
                  {availableBuiltinAgents.length === 0 ? (
                    <li className="aw-tools-empty">{t("agent.workbench.allBuiltinAdded", { ns: "settings" })}</li>
                  ) : (
                    availableBuiltinAgents.map((id) => (
                      <li key={id}>
                        <button
                          type="button"
                          className="aw-builtin-agent-btn"
                          onClick={() => {
                            addBuiltinAgentToProfile(id);
                            closeNewAgentModal();
                          }}
                        >
                          <span className="aw-tool-name">{id}</span>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              ) : (
                <>
              <label className="aw-field">
                {t("agent.workbench.agentId", { ns: "settings" })}
                <input
                  autoFocus
                  placeholder="my_script_agent"
                  value={newAgentId}
                  onChange={(e) => setNewAgentId(e.target.value)}
                />
              </label>
              <label className="aw-field">
                {t("agent.workbench.label", { ns: "settings" })}
                <input
                  placeholder={t("agent.workbench.labelPlaceholder", { ns: "settings" })}
                  value={newAgentLabel}
                  onChange={(e) => setNewAgentLabel(e.target.value)}
                />
              </label>
              <label className="aw-field">
                {t("agent.workbench.agentTemplate", { ns: "settings" })}
                <select
                  value={newAgentBasedOn}
                  onChange={(e) => setNewAgentBasedOn(e.target.value)}
                >
                  {CLONABLE_AGENT_TEMPLATES.map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
                </select>
              </label>
                </>
              )}
            </div>
            <footer className="aw-modal-foot">
              <button type="button" className="aw-btn-ghost" onClick={closeNewAgentModal}>
                {t("actions.cancel", { ns: "common" })}
              </button>
              {newAgentModalTab === "custom" && (
              <button
                type="button"
                className="aw-save-btn aw-modal-submit"
                disabled={!newAgentId.trim()}
                onClick={handleCreateAgentFromModal}
              >
                {t("agent.workbench.createAgent", { ns: "settings" })}
              </button>
              )}
            </footer>
          </div>
        </div>
      )}

      {showToolPicker && selectedAgentInfo && (
        <div
          className="aw-tool-picker-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeToolPicker();
          }}
        >
          <aside
            className={`aw-tool-picker-drawer${inspectedTool ? " has-detail" : ""}${toolPickerResize.isResizable ? " is-resizable" : ""}`}
            style={toolPickerResize.drawerStyle}
            role="dialog"
            aria-modal="true"
            aria-labelledby="aw-tool-picker-title"
            onClick={(e) => e.stopPropagation()}
          >
            {toolPickerResize.isResizable ? (
              <ResizableDrawerEdge
                onPointerDown={toolPickerResize.onResizePointerDown}
                label={t("actions.resizeDrawer", { ns: "common" })}
              />
            ) : null}
            <header className="aw-tool-picker-head">
              <div className="aw-tool-picker-head-main">
                <p className="aw-modal-eyebrow">{selectedAgentInfo.display_name}</p>
                <h2 id="aw-tool-picker-title" className="aw-modal-title">
                  {t("agent.workbench.addToolModalTitle", { ns: "settings" })}
                </h2>
                <p className="aw-modal-desc">{t("agent.workbench.addToolModalDesc", { ns: "settings" })}</p>
              </div>
              <button
                type="button"
                className="aw-btn-ghost aw-tool-picker-close"
                onClick={closeToolPicker}
                aria-label={t("actions.cancel", { ns: "common" })}
              >
                ×
              </button>
            </header>
            <div className="aw-tool-picker-toolbar">
              <input
                className="aw-tool-search"
                placeholder={t("agent.workbench.searchTools", { ns: "settings" })}
                value={toolSearchQuery}
                onChange={(e) => setToolSearchQuery(e.target.value)}
              />
              <span className="aw-tool-picker-count">
                {t("agent.workbench.toolPickerCount", { ns: "settings", count: addableTools.length })}
              </span>
            </div>
            <div className="aw-tool-picker-layout">
              <div className="aw-tool-picker-body">
                {renderGroupedToolCatalog(
                  addableToolLayout,
                  (action) => addSelectedTool(selectedAgentInfo, action),
                  t("agent.workbench.noToolsToAdd", { ns: "settings" }),
                  setInspectedTool,
                )}
              </div>
              {inspectedTool && (
                <ToolSchemaDetailPanel
                  tool={inspectedTool}
                  onClose={() => setInspectedTool(null)}
                  translateScope={translateToolScope}
                  translateOperation={translateToolOperation}
                />
              )}
            </div>
            <footer className="aw-tool-picker-foot">
              <button type="button" className="aw-save-btn aw-modal-submit" onClick={closeToolPicker}>
                {t("agent.workbench.addToolDrawerDone", { ns: "settings" })}
              </button>
            </footer>
          </aside>
        </div>
      )}

      {showSkillPicker && selectedAgentInfo && (
        <div
          className="aw-tool-picker-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeSkillPicker();
          }}
        >
          <aside
            className="aw-tool-picker-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aw-skill-picker-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="aw-tool-picker-head">
              <div className="aw-tool-picker-head-main">
                <p className="aw-modal-eyebrow">{selectedAgentInfo.display_name}</p>
                <h2 id="aw-skill-picker-title" className="aw-modal-title">
                  {t("agent.workbench.addSkillModalTitle", { ns: "settings" })}
                </h2>
                <p className="aw-modal-desc">{t("agent.workbench.addSkillModalDesc", { ns: "settings" })}</p>
                <p className="aw-skill-picker-thesis">
                  {t("agent.workbench.addSkillThesis", { ns: "settings" })}
                </p>
              </div>
              <button
                type="button"
                className="aw-btn-ghost aw-tool-picker-close"
                onClick={closeSkillPicker}
                aria-label={t("actions.cancel", { ns: "common" })}
              >
                ×
              </button>
            </header>
            <div className="aw-tool-picker-toolbar">
              <input
                className="aw-tool-search"
                placeholder={t("agent.workbench.searchSkills", { ns: "settings" })}
                value={skillSearchQuery}
                onChange={(e) => setSkillSearchQuery(e.target.value)}
              />
              <span className="aw-tool-picker-count">
                {t("agent.workbench.skillPickerCount", {
                  ns: "settings",
                  count: addableSkills.length,
                })}
              </span>
            </div>
            <div className="aw-tool-picker-layout">
              <div className="aw-tool-picker-body">
                {addableSkills.length === 0 ? (
                  <p className="aw-tools-empty">
                    {t("agent.workbench.noSkillsToAdd", { ns: "settings" })}
                  </p>
                ) : (
                  <ul className="aw-skill-pick-list">
                    {addableSkills.map((skill) => (
                      <li key={skill.id}>
                        <button
                          type="button"
                          className="aw-skill-pick-card"
                          onClick={() => addSelectedSkill(selectedAgentInfo.name, skill.id)}
                        >
                          <span className="aw-skill-pick-sprocket" aria-hidden />
                          <span className="aw-skill-pick-body">
                            <span className="aw-skill-pick-top">
                              <span className="aw-skill-pick-title">{skill.title || skill.id}</span>
                              {skill.source ? (
                                <span className={`aw-skill-source aw-skill-source-${skill.source}`}>
                                  {skill.source}
                                </span>
                              ) : null}
                            </span>
                            <span className="aw-skill-pick-slashes">
                              {[skill.id, ...(skill.aliases || [])]
                                .slice(0, 4)
                                .map((a) => `/${a}`)
                                .join(" · ")}
                            </span>
                            {skill.description ? (
                              <span className="aw-skill-pick-purpose">{skill.description}</span>
                            ) : (
                              <span className="aw-skill-pick-purpose aw-skill-pick-purpose-muted">
                                {t("agent.workbench.skillNoPurpose", { ns: "settings" })}
                              </span>
                            )}
                            <span className="aw-skill-pick-effects">
                              {(skill.highlights && skill.highlights.length > 0
                                ? skill.highlights
                                : [
                                    t("agent.workbench.skillEffectInject", { ns: "settings" }),
                                    t("agent.workbench.skillEffectRefs", { ns: "settings" }),
                                  ]
                              ).map((h) => (
                                <span key={h} className="aw-skill-effect-chip">
                                  {h}
                                </span>
                              ))}
                            </span>
                            <span className="aw-skill-pick-cta">
                              {t("agent.workbench.addSkillToAgent", { ns: "settings" })}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <footer className="aw-tool-picker-foot">
              <button type="button" className="aw-save-btn aw-modal-submit" onClick={closeSkillPicker}>
                {t("agent.workbench.addToolDrawerDone", { ns: "settings" })}
              </button>
            </footer>
          </aside>
        </div>
      )}
    </AppShell>
  );
}
