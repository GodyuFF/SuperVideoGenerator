/** Agent 配置 API 类型 */

export interface PromptProfileOption {
  id: string;
  label: string;
}

export interface AgentToolInfo {
  name: string;
  description: string;
  action: string | null;
  read_only: boolean;
}

export interface AgentInfo {
  name: string;
  display_name: string;
  action_pipeline: string[];
  ad_hoc_actions: string[];
  read_actions: string[];
  prompt_profile: string | null;
  effective_role_prompt: string;
  action_hint: string;
  tools: AgentToolInfo[];
}

export interface AgentConfigResponse {
  prompt_profiles: Record<string, string>;
  available_profiles: PromptProfileOption[];
  agents: AgentInfo[];
}

export interface AgentConfigPatch {
  prompt_profiles?: Record<string, string>;
}

export interface MediaAsset {
  id: string;
  project_id: string;
  script_id: string | null;
  type: "image" | "video" | "audio" | "final";
  name: string;
  url: string;
  source_asset_id: string | null;
  status: string;
}
