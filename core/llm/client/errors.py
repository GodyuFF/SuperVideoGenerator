"""LLM 调用错误文案。"""

import httpx


def format_llm_http_error(
    error: Exception,
    *,
    url: str,
    provider: str,
) -> str:
    """将 httpx 异常转为用户可理解的说明。"""
    if isinstance(error, httpx.ConnectError):
        return (
            f"无法连接 {provider} API（{url}）。"
            "请检查：① 网络是否正常 ② AI 配置中的 base_url 是否正确"
            "（DeepSeek 一般为 https://api.deepseek.com）"
            "③ 若使用代理，可设置环境变量 SVG_LLM_TRUST_ENV=true 或关闭系统代理。"
            f"技术详情：{error}"
        )
    if isinstance(error, httpx.TimeoutException):
        return (
            f"连接 {provider} API 超时（{url}）。"
            "请稍后重试或增大 SVG_LLM_TIMEOUT_SEC。"
        )
    return f"LLM 请求失败（{provider}）：{error}"
