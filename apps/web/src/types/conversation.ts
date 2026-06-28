/** 对话线程元数据（项目级历史列表） */

export interface ConversationSummary {
  id: string;
  script_id: string;
  title: string;
  last_summary: string;
  created_at: string;
  updated_at: string;
  status: string;
  last_round_token_usage?: {
    total_tokens?: number;
    models?: Array<{ model: string; total_tokens: number }>;
  };
  total_token_usage?: Record<string, number>;
}

export interface ConversationMessageRecord {
  role: "user" | "master";
  content: string;
  created_at: string;
}
