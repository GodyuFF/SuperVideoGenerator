/**
 * 前后端共享的类型定义：A2UI、WebSocket 事件、资产与计划步骤。
 */

/** A2UI 表单单个组件描述 */
export interface A2UIComponent {
  id: string;
  component: "text" | "markdown" | "select" | "checkbox" | "cost_summary";
  label: string;
  value?: unknown;
  options?: { label: string; value: string }[];
  required?: boolean;
}

/** 服务端推送的 A2UI 确认请求 */
export interface A2UIConfirmationRequest {
  type: "a2ui_confirmation_required";
  confirmation_id: string;
  kind: string;
  title: string;
  description?: string;
  components: A2UIComponent[];
  estimated_cost_usd?: number;
  expires_in_sec?: number;
  step_id?: string;
}

/** WebSocket 事件（通用字典） */
export type WsEvent = Record<string, unknown>;

/** Plan 执行步骤 */
export interface PlanStep {
  id: string;
  type: string;
  title: string;
  status: string;
  error?: string;
}

/** 文字资产 */
export interface TextAsset {
  id: string;
  name: string;
  type: string;
  scope: string;
  content: Record<string, unknown>;
}

/** LLM 服务商选项 */
export interface LLMProviderOption {
  id: string;
  label: string;
  default_model: string;
}

/** LLM 公开配置（GET /api/llm/config） */
export interface LLMConfig {
  provider: string;
  provider_label: string;
  model: string;
  base_url: string;
  temperature: number;
  max_tokens: number;
  use_llm_react: boolean;
  has_api_key: boolean;
  llm_active: boolean;
  available_providers: LLMProviderOption[];
}

/** PATCH /api/llm/config 请求体 */
export interface LLMConfigPatch {
  provider?: string;
  model?: string;
  api_key?: string;
  base_url?: string;
  use_llm_react?: boolean;
  temperature?: number;
  max_tokens?: number;
}
