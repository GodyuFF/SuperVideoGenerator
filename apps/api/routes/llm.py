"""LLM 配置 API（兼容旧版；推荐使用 /api/ai/config）。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.state import state
from core.models.entities import ImageSourceMode

router = APIRouter(prefix="/api/llm")


class UpdateLLMConfigRequest(BaseModel):
    """更新 LLM 配置（Key 仅写入服务端内存，不落库）。"""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = Field(None, description="API Key，留空表示不修改")
    base_url: str | None = None
    use_llm_react: bool | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    image_source_default: ImageSourceMode | None = None
    image_text_preset: str | None = None
    comic_preset: str | None = None
    image_batch_pending_assets: bool | None = None
    image_allow_search_fallback: bool | None = None


@router.get("/config")
def get_llm_config():
    """获取 LLM 配置（扁平结构，兼容旧前端）。"""
    return state.ai_config.get_llm_legacy_config()


@router.patch("/config")
def patch_llm_config(body: UpdateLLMConfigRequest):
    """运行时更新 LLM 与图文流水线默认项（兼容旧 API）。"""
    try:
        return state.ai_config.patch_llm_legacy(**body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
