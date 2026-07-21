"""生图失败结构化解析与主编排 observation 格式化。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from core.store.memory import MemoryStore

# 主编排 observation 中单条 prompt 摘要上限
PROMPT_PREVIEW_CHARS = 240


@dataclass(frozen=True)
class ImageGenFailureItem:
    """单项文字资产生图失败详情。"""

    source_text_asset_id: str
    asset_name: str
    error_category: str
    error_code: str
    error_message: str
    image_prompt_preview: str
    attempts: int = 3
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def needs_upstream_prompt_adjustment(self) -> bool:
        return self.error_category in {"content_policy", "invalid_prompt"}


@dataclass(frozen=True)
class ImageGenFailureAnalysis:
    """汇总全部失败项与主编排建议。"""

    failures: tuple[ImageGenFailureItem, ...]
    succeeded_count: int = 0
    total_count: int = 0

    @property
    def failed_count(self) -> int:
        return len(self.failures)

    def needs_upstream_prompt_adjustment(self) -> bool:
        return any(item.needs_upstream_prompt_adjustment for item in self.failures)

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.failures:
            counts[item.error_category] = counts.get(item.error_category, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "failed_count": self.failed_count,
            "succeeded_count": self.succeeded_count,
            "total_count": self.total_count,
            "category_counts": self.category_counts(),
            "needs_upstream_prompt_adjustment": self.needs_upstream_prompt_adjustment(),
            "failures": [item.to_dict() for item in self.failures],
        }


_CATEGORY_LABELS: dict[str, str] = {
    "content_policy": "内容策略违规",
    "invalid_prompt": "提示词无效/不合规",
    "auth": "API Key 或鉴权失败",
    "network": "网络或超时",
    "rate_limit": "频率/配额限制",
    "server": "服务端错误",
    "unknown": "未知错误",
}


def category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def classify_image_gen_error(
    *,
    message: str,
    error_code: str = "",
    error_type: str = "",
    param: str = "",
    http_status: int | None = None,
) -> str:
    """将 Agnes/OpenAI 兼容错误映射为内部 category。"""
    code = (error_code or "").strip().lower()
    err_type = (error_type or "").strip().lower()
    param_l = (param or "").strip().lower()
    msg_l = (message or "").strip().lower()

    if code in {"content_policy_violation", "content_filter"} or "content policy" in msg_l:
        return "content_policy"
    if code in {"invalid_api_key", "authentication_error", "permission_denied"}:
        return "auth"
    if (
        http_status == 429
        or code in {"rate_limit_exceeded", "insufficient_quota", "throttling.ratequota"}
        or "rate limit" in msg_l
        or "throttling" in msg_l
        or "ratequota" in code.replace("_", "").replace(".", "")
    ):
        return "rate_limit"
    if err_type == "invalid_request_error" and param_l == "prompt":
        return "invalid_prompt"
    if "invalid_request" in err_type and "prompt" in msg_l:
        return "invalid_prompt"
    if http_status is not None and http_status >= 500:
        return "server"
    if "网络" in message or "timeout" in msg_l or "timed out" in msg_l:
        return "network"
    if "api key" in msg_l or "未配置" in message:
        return "auth"
    return "unknown"


def parse_agnes_api_error_body(status_code: int, body_text: str) -> dict[str, str]:
    """从 Agnes HTTP 错误体提取 message/code/type/param。"""
    api_message = ""
    error_code = ""
    error_type = ""
    param = ""
    try:
        parsed = json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, dict):
            api_message = str(err.get("message") or "").strip()
            error_code = str(err.get("code") or "").strip()
            error_type = str(err.get("type") or "").strip()
            param = str(err.get("param") or "").strip()
        elif isinstance(err, str):
            api_message = err.strip()
    display = api_message or body_text.strip()[:500]
    return {
        "message": display,
        "error_code": error_code,
        "error_type": error_type,
        "param": param,
    }


def build_failure_item(
    *,
    source_text_asset_id: str,
    asset_name: str,
    image_prompt: str,
    error_message: str,
    error_code: str = "",
    error_type: str = "",
    param: str = "",
    http_status: int | None = None,
    attempts: int = 3,
) -> ImageGenFailureItem:
    preview = image_prompt.strip()
    if len(preview) > PROMPT_PREVIEW_CHARS:
        preview = preview[:PROMPT_PREVIEW_CHARS] + "…"
    category = classify_image_gen_error(
        message=error_message,
        error_code=error_code,
        error_type=error_type,
        param=param,
        http_status=http_status,
    )
    return ImageGenFailureItem(
        source_text_asset_id=source_text_asset_id,
        asset_name=asset_name or source_text_asset_id,
        error_category=category,
        error_code=error_code,
        error_message=error_message.strip(),
        image_prompt_preview=preview,
        attempts=attempts,
        http_status=http_status,
    )


def build_image_gen_failure_analysis(
    failures: list[ImageGenFailureItem],
    *,
    succeeded_count: int = 0,
    total_count: int = 0,
) -> ImageGenFailureAnalysis:
    return ImageGenFailureAnalysis(
        failures=tuple(failures),
        succeeded_count=succeeded_count,
        total_count=total_count or (succeeded_count + len(failures)),
    )


def format_image_gen_abort_message(analysis: ImageGenFailureAnalysis) -> str:
    """用于 step.error / ImageGenerationAbortError 的摘要（含全部失败项）。"""
    lines = [
        f"图片生成失败：{analysis.failed_count}/{analysis.total_count} 项在重试后仍失败。",
    ]
    counts = analysis.category_counts()
    if counts:
        summary = "；".join(
            f"{category_label(cat)} {n} 项" for cat, n in sorted(counts.items())
        )
        lines.append(f"原因分布：{summary}。")
    for idx, item in enumerate(analysis.failures, start=1):
        lines.append(
            f"{idx}. {item.source_text_asset_id}「{item.asset_name}」"
            f" — {category_label(item.error_category)}"
            f"{f' ({item.error_code})' if item.error_code else ''}"
            f"：{item.error_message}"
        )
    return "\n".join(lines)


def format_image_gen_failure_observation(
    analysis: ImageGenFailureAnalysis,
    *,
    agent_display_name: str = "图片 Agent",
    step_title: str = "图片素材生成",
) -> str:
    """主编排 ReAct observation：含全部失败原因与处置建议。"""
    header = (
        f"委派 {agent_display_name} 失败，步骤「{step_title}」未完成。"
        f" 成功 {analysis.succeeded_count} 项，失败 {analysis.failed_count} 项。"
    )
    blocks = [header, "", "【失败明细（全部）】"]
    for idx, item in enumerate(analysis.failures, start=1):
        blocks.extend(
            [
                f"{idx}. 资产 {item.source_text_asset_id}「{item.asset_name}」",
                f"   - 原因分类：{category_label(item.error_category)}"
                + (f" ({item.error_code})" if item.error_code else ""),
                f"   - API 说明：{item.error_message}",
                f"   - image_prompt 摘要：{item.image_prompt_preview or '（空）'}",
                f"   - 已重试：{item.attempts} 次",
            ]
        )
    blocks.append("")
    blocks.append("【主编排需分析并决策】")
    if analysis.needs_upstream_prompt_adjustment():
        blocks.append(
            "- 存在内容策略/提示词类失败：应 delegate_agent(agent_id=script_agent)，"
            "请 script_agent 修订相关文字资产的 description、prompt_hint（必要时 update_scene/update_character），"
            "去除暴力、猎食、血腥、真实人物等敏感表述后再 delegate_agent(agent_id=image_agent)。"
        )
        blocks.append(
            "- 已将 script_design 步骤重新开放，可再次委派 script_agent。"
        )
    else:
        blocks.append(
            "- 失败主要为鉴权/网络/服务端问题：检查 AI 配置中的生图 API Key 与网络，"
            "排除故障后可重试 delegate_agent(agent_id=image_agent)；无需修改剧本提示词。"
        )
    blocks.append(
        "- 在 thought 中简要说明失败原因归类与你的下一步选择（修 prompt / 重试生图 / 询问用户）。"
    )
    return "\n".join(blocks)


def enrich_failure_names(
    store: MemoryStore,
    failures: list[ImageGenFailureItem],
) -> list[ImageGenFailureItem]:
    """用 store 补全资产名称（若仅有 id）。"""
    enriched: list[ImageGenFailureItem] = []
    for item in failures:
        name = item.asset_name
        if not name or name == item.source_text_asset_id:
            asset = store.get_text_asset(item.source_text_asset_id)
            if asset and asset.name:
                name = asset.name
        if name == item.asset_name:
            enriched.append(item)
            continue
        enriched.append(
            ImageGenFailureItem(
                source_text_asset_id=item.source_text_asset_id,
                asset_name=name,
                error_category=item.error_category,
                error_code=item.error_code,
                error_message=item.error_message,
                image_prompt_preview=item.image_prompt_preview,
                attempts=item.attempts,
                http_status=item.http_status,
            )
        )
    return enriched
