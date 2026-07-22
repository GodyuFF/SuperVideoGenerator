/** Agent 配置 API 类型（提示词工作台） */

export interface PromptProfileOption {
  id: string;
  label: string;
  builtin?: boolean;
  deletable?: boolean;
  editable?: boolean;
  restorable?: boolean;
}

export interface CustomPromptProfile {
  id: string;
  label: string;
  based_on?: string | null;
}

export type StyleVideoGenMode = "text2video" | "img2video" | "keyframes";

/** JSON Schema 对象（工具入参/出参）。 */
export type JsonSchemaObject = Record<string, unknown>;

export interface StyleModeOption {
  id: string;
  label: string;
  default_prompt_profile: string;
  include_video_gen: boolean;
  /** 允许的 AI 生视频子模式；空表示不可 AI 生视频。 */
  video?: StyleVideoGenMode[];
  builtin: boolean;
}

export interface AgentPromptContentOverride {
  role_prompt?: string | null;
  action_hint?: string | null;
}

export interface AgentToolOverride {
  include_only?: string[] | null;
  exclude?: string[] | null;
}

export interface AgentToolInfo {
  name: string;
  description: string;
  action: string | null;
  read_only: boolean;
  kind?: string;
}

export interface CustomAgentDefinition {
  id: string;
  label: string;
  based_on: string;
}

export interface AgentToolOption {
  name: string;
  action: string;
  description: string;
  kind: string;
  read_only: boolean;
  scopes?: string[];
  operations?: string[];
  asset_layer?: string;
  affected_data_read?: string[];
  affected_data_write?: string[];
  boundary_note?: string;
  may_write_edit_timeline?: boolean;
  multi_scope_read?: boolean;
  /** 所属 Agent（全局 catalog 项）。 */
  agent?: string;
  /** LLM 调用入参 JSON Schema。 */
  input_schema?: JsonSchemaObject;
  /** 工具返回 observation JSON Schema。 */
  output_schema?: JsonSchemaObject;
}

export interface AgentInfo {
  name: string;
  display_name: string;
  builtin?: boolean;
  based_on?: string | null;
  action_pipeline: string[];
  ad_hoc_actions: string[];
  read_actions: string[];
  prompt_profile: string | null;
  effective_role_prompt: string;
  action_hint: string;
  tools: AgentToolInfo[];
  tool_options?: AgentToolOption[];
  system_tools?: AgentToolOption[];
  all_tools?: string[];
  effective_tools?: string[];
}

export interface AgentConfigResponse {
  prompt_profiles: Record<string, string>;
  custom_profiles: CustomPromptProfile[];
  style_modes: StyleModeOption[];
  prompt_content: Record<string, Record<string, AgentPromptContentOverride>>;
  tool_overrides: Record<string, AgentToolOverride>;
  custom_agents: CustomAgentDefinition[];
  profile_agents: Record<string, string[]>;
  tool_overrides_by_profile: Record<string, Record<string, AgentToolOverride>>;
  /** profile → agent → 可用 skill id；缺省 agent 键表示可用全部 */
  skill_allowlists_by_profile?: Record<string, Record<string, string[]>>;
  available_profiles: PromptProfileOption[];
  config_path?: string;
  agents: AgentInfo[];
}

export interface AgentConfigPatch {
  prompt_profiles?: Record<string, string>;
  custom_profiles?: CustomPromptProfile[];
  style_modes?: StyleModeOption[];
  prompt_content?: Record<string, Record<string, AgentPromptContentOverride>>;
  tool_overrides?: Record<string, AgentToolOverride>;
  custom_agents?: CustomAgentDefinition[];
  profile_agents?: Record<string, string[]>;
  tool_overrides_by_profile?: Record<string, Record<string, AgentToolOverride>>;
  skill_allowlists_by_profile?: Record<string, Record<string, string[]>>;
}

/** Skill 列表项（配置页 / Workbench） */
export interface SkillMetaItem {
  id: string;
  title: string;
  description?: string;
  aliases?: string[];
  /** 作用亮点（添加抽屉突出展示） */
  highlights?: string[];
  source?: string;
  deletable?: boolean;
}

export interface AgentPromptResponse {
  agent: string;
  profile: string;
  role_prompt: string;
  action_hint: string;
  source: { role_prompt: string; action_hint: string };
}

export interface ToolsCatalogResponse {
  governance?: {
    edit_timeline_write_agent: string;
    rules: string[];
  };
  catalog?: AgentToolOption[];
  agents: Record<string, AgentToolOption[]>;
  registry_version?: number;
}

export interface StyleModesResponse {
  style_modes: StyleModeOption[];
}
