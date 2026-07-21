"""接口交互记录实体。"""

from typing import Any

from pydantic import BaseModel, Field

from core.models.entities import new_id


class InteractionRecord(BaseModel):
    """单条持久化交互记录。"""

    id: str = Field(default_factory=lambda: new_id("ilog"))
    created_at: str = ""
    kind: str  # llm_request | llm_response | llm_error | conversation_token_round | agent_action | api_request | media_http
    source: str = ""  # llm | agent | http
    project_id: str = ""
    script_id: str = ""
    agent_name: str = ""
    step_id: str = ""
    provider: str = ""
    model: str = ""
    method: str = ""
    url: str = ""
    status_code: int | None = None
    duration_ms: float | None = None
    summary: str = ""
    request_body: dict[str, Any] | None = None
    response_body: dict[str, Any] | str | None = None
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
