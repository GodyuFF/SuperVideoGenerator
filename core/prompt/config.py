"""提示词上下文滑窗与压缩配置。"""

# 送入 LLM 的 observation 条数上限（保留最近 N 条）
OBSERVATION_WINDOW_SIZE = 8

# observation 总字符预算
OBSERVATION_MAX_CHARS = 6000

# 会话历史（thought/action/observation）条数上限
HISTORY_WINDOW_SIZE = 16

# 会话历史字符预算
HISTORY_MAX_CHARS = 5000

# 被压缩条目的摘要长度（每条）
COMPRESSION_SNIPPET_CHARS = 100

# 剧本正文注入上下文的字符上限
SCRIPT_MD_CONTEXT_MAX = 2000

# 单条资产摘要字符上限
ASSET_SUMMARY_MAX = 120
