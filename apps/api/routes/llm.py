"""LLM 配置 API：查看/切换服务商与模型。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.api.state import state

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


@router.get("/config")
def get_llm_config():
    """获取当前 LLM 配置与可用服务商列表。"""
    return state.llm_config.get_public_config()


@router.patch("/config")
def patch_llm_config(body: UpdateLLMConfigRequest):
    """运行时更新 LLM 配置（默认 DeepSeek，可切换主流模型）。"""
    try:
        return state.llm_config.update(
            provider=body.provider,
            model=body.model,
            api_key=body.api_key,
            base_url=body.base_url,
            use_llm_react=body.use_llm_react,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
