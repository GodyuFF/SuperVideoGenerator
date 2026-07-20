"""UI 偏好 REST：界面语言跨 Electron / 浏览器单源。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.prefs.ui_prefs import UiPrefsError, load_ui_prefs, patch_ui_prefs

router = APIRouter(prefix="/api/ui-prefs", tags=["ui-prefs"])


class PatchUiPrefsRequest(BaseModel):
    """UI 偏好 PATCH 体。"""

    ui_locale: str | None = Field(None, description="界面语言：zh-CN | en")


@router.get("")
def get_ui_prefs() -> dict[str, Any]:
    """读取本机 UI 偏好（界面语言等）。"""
    return load_ui_prefs()


@router.patch("")
def patch_ui_prefs_route(body: PatchUiPrefsRequest) -> dict[str, Any]:
    """更新本机 UI 偏好并落盘到 data/ui_prefs.json。"""
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        return load_ui_prefs()
    try:
        return patch_ui_prefs(payload)
    except UiPrefsError as exc:
        raise HTTPException(400, str(exc)) from exc
