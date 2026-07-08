"""统一 AI 配置 API：LLM / 图片 / 视频 / TTS。"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from apps.api.state import state
from core.llm.ai_config_store import collect_persisted_config, save_ai_config
from core.models.entities import ImageSourceMode
from core.store.project_paths import DATA_ROOT
from core.tts.engine import is_tts_available, synthesize_speech
from core.tts.voices import get_all_voices
from core.llm.tools.image.settings import get_image_gen_manager

router = APIRouter(prefix="/api/ai")

_PREVIEW_DIR = DATA_ROOT / "temp" / "tts_preview"
_TEST_IMAGE_DIR = DATA_ROOT / "temp" / "test_images"


class ImagePipelinePatch(BaseModel):
    source_mode: ImageSourceMode | None = None
    image_text_preset: str | None = None
    comic_preset: str | None = None
    batch_pending_assets: bool | None = None
    allow_search_fallback: bool | None = None


class LlmSectionPatch(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = Field(None, description="API Key，留空表示不修改")
    base_url: str | None = None
    use_llm_react: bool | None = None
    show_react_details: bool | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ImageSectionPatch(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = Field(None, description="生图 API Key，留空表示不修改")
    base_url: str | None = None
    default_size: str | None = None
    timeout_sec: float | None = None
    sd_base_url: str | None = None
    sd_steps: int | None = None
    sd_cfg_scale: float | None = None
    sd_sampler: str | None = None
    sd_negative_prompt: str | None = None
    bailian_workspace_id: str | None = None
    bailian_txt2img_model: str | None = None
    bailian_img2img_model: str | None = None
    pipeline: ImagePipelinePatch | None = None


class VideoSectionPatch(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = Field(None, description="视频 API Key，留空表示不修改")
    base_url: str | None = None
    max_duration_sec: int | None = None
    resolution: str | None = None
    timeout_sec: float | None = None


class TtsSectionPatch(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = Field(None, description="TTS API Key，留空表示不修改")
    base_url: str | None = None
    default_language: str | None = None
    default_voice: str | None = None
    voice_rate: float | None = None
    voice_volume: float | None = None
    sample_rate: int | None = None
    timeout_sec: float | None = None
    edge_tts_timeout_sec: float | None = None
    max_concurrency: int | None = None
    ffmpeg_path: str | None = None
    gemini_api_key: str | None = Field(None, description="Gemini API Key，留空表示不修改")
    mimo_api_key: str | None = Field(None, description="MiMo API Key，留空表示不修改")
    mimo_base_url: str | None = None
    mimo_tts_model: str | None = None
    mimo_style_prompt: str | None = None
    siliconflow_api_key: str | None = Field(None, description="SiliconFlow API Key，留空表示不修改")
    azure_speech_key: str | None = Field(None, description="Azure Speech Key，留空表示不修改")
    azure_speech_region: str | None = None


class ExportSectionPatch(BaseModel):
    enabled: bool | None = None
    ffmpeg_path: str | None = None
    fps: int | None = None
    width: int | None = None
    height: int | None = None
    crf: int | None = None


class UpdateAiConfigRequest(BaseModel):
    llm: LlmSectionPatch | None = None
    image: ImageSectionPatch | None = None
    video: VideoSectionPatch | None = None
    tts: TtsSectionPatch | None = None
    export: ExportSectionPatch | None = None


class TtsPreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100)
    voice_name: str | None = None
    voice_rate: float | None = None
    voice_volume: float | None = None
    provider: str | None = None
    default_language: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = Field(None, description="OpenAI TTS Key，留空则用已保存配置")
    gemini_api_key: str | None = None
    mimo_api_key: str | None = None
    siliconflow_api_key: str | None = None
    azure_speech_key: str | None = None
    azure_speech_region: str | None = None


def _tts_preview_unavailable_reason(runtime) -> str:
    settings = runtime.settings
    voice = (runtime.voice_name or "").strip()
    if settings.provider == "openai" and not runtime.resolved_api_key:
        return "OpenAI TTS 需要 API Key（可在表单填写或保存配置）"
    if voice.startswith("siliconflow:") and not settings.siliconflow_api_key:
        return "SiliconFlow 音色需要 SiliconFlow API Key"
    if voice.startswith("gemini:") and not settings.gemini_api_key:
        return "Gemini 音色需要 Gemini API Key"
    if voice.startswith("mimo:") and not settings.mimo_api_key:
        return "MiMo 音色需要 MiMo API Key"
    if voice.startswith("azure:") and (
        not settings.azure_speech_key or not settings.azure_speech_region
    ):
        return "Azure 音色需要 Speech Key 与 Region"
    return "当前 TTS 配置无法试听，请检查 provider、音色与 API Key"


def _section_dict(section: BaseModel | None) -> dict[str, Any] | None:
    if section is None:
        return None
    data = section.model_dump(exclude_none=True)
    pipeline = data.pop("pipeline", None)
    if pipeline:
        data["pipeline"] = pipeline
    return data or None


@router.get("/config")
def get_ai_config():
    """获取 LLM / 图片 / 视频 / TTS 分区配置。"""
    return state.ai_config.get_public_config()


@router.patch("/config")
def patch_ai_config(body: UpdateAiConfigRequest):
    """更新 AI 配置并持久化到 data/ai_config.json（含 API Key，仅本机 data/ 目录）。"""
    try:
        return state.ai_config.update(
            llm=_section_dict(body.llm),
            image=_section_dict(body.image),
            video=_section_dict(body.video),
            tts=_section_dict(body.tts),
            export=_section_dict(body.export),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/tts/voices")
def list_tts_voices(locale: str | None = Query(None, description="语言区域过滤，如 zh-CN")):
    """返回可选 TTS 音色列表。"""
    return {"voices": get_all_voices(locale)}


@router.post("/tts/preview")
def preview_tts(body: TtsPreviewRequest):
    """短文本 TTS 试听，返回临时 mp3 URL（不依赖 TTS enabled 开关）。"""
    runtime = state.ai_config.tts.preview_runtime_config(
        provider=body.provider,
        voice_name=body.voice_name,
        voice_rate=body.voice_rate,
        voice_volume=body.voice_volume,
        default_language=body.default_language,
        model=body.model,
        base_url=body.base_url,
        api_key=body.api_key,
        gemini_api_key=body.gemini_api_key,
        mimo_api_key=body.mimo_api_key,
        siliconflow_api_key=body.siliconflow_api_key,
        azure_speech_key=body.azure_speech_key,
        azure_speech_region=body.azure_speech_region,
    )
    if not is_tts_available(runtime):
        raise HTTPException(400, detail=_tts_preview_unavailable_reason(runtime))
    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.mp3"
    output_path = _PREVIEW_DIR / filename
    sub_maker = synthesize_speech(
        body.text,
        str(output_path),
        runtime,
        voice_name=body.voice_name,
        voice_rate=body.voice_rate,
        voice_volume=body.voice_volume,
    )
    if sub_maker is None or not output_path.is_file():
        raise HTTPException(502, detail="TTS 试听合成失败")
    return {
        "ok": True,
        "url": f"/api/ai/tts/preview/{filename}",
        "filename": filename,
    }


@router.get("/tts/preview/{filename}")
def get_tts_preview_file(filename: str):
    """读取试听临时 mp3 文件。"""
    safe = Path(filename).name
    path = _PREVIEW_DIR / safe
    if not path.is_file():
        raise HTTPException(404, detail="试听文件不存在或已过期")
    return FileResponse(path, media_type="audio/mpeg", filename=safe)


class TestImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="生图提示词")


@router.post("/image/test")
async def test_image_generation(body: TestImageRequest):
    """使用当前图片配置测试生成一张图片，返回临时图片 URL。

    - 若 provider=local_sd：调用本地 SD txt2img
    - 若 provider=agnes：调用 Agnes API txt2img
    """
    from core.llm.tools.image.agnes_client import (
        AgnesImageGenerationError,
        generate_text_to_image_async,
    )
    from core.llm.tools.image.sd_client import (
        SdImageGenerationError,
        sd_txt2img,
    )
    from core.llm.tools.image.settings import get_image_gen_settings

    settings = get_image_gen_settings()
    if not settings.enabled:
        raise HTTPException(400, detail="图片生成未启用")

    try:
        if settings.provider == "local_sd":
            # SD 生图时，在用户 prompt 前添加质量前缀，提升输出质量
            sd_prompt = f"{body.prompt.strip()}, masterpiece, best quality, highly detailed"
            image_url = await sd_txt2img(
                sd_prompt,
                settings=settings,
                timeout=120.0,
            )
        elif settings.provider == "bailian":
            from core.llm.tools.image.bailian_client import (
                BailianImageGenerationError,
                bailian_txt2img,
            )
            image_url = await bailian_txt2img(
                body.prompt,
                settings=settings,
            )
        else:
            image_url = await generate_text_to_image_async(
                body.prompt,
                settings=settings,
            )
    except SdImageGenerationError as e:
        raise HTTPException(502, detail=f"本地 SD 生图失败：{e}") from e
    except AgnesImageGenerationError as e:
        raise HTTPException(502, detail=f"Agnes 生图失败：{e}") from e
    except BailianImageGenerationError as e:
        raise HTTPException(502, detail=f"百炼生图失败：{e}") from e
    except Exception as e:
        raise HTTPException(502, detail=f"生图失败：{e}") from e

    # 将 base64 data URL 保存到磁盘（如果是 data: URL）
    import base64

    _TEST_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    output_path = _TEST_IMAGE_DIR / filename

    if image_url.startswith("data:"):
        _, _, b64_part = image_url.partition("base64,")
        if b64_part:
            img_data = base64.b64decode(b64_part)
            output_path.write_bytes(img_data)
    else:
        # 远程 URL，下载保存
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)

    return {
        "ok": True,
        "url": f"/api/ai/image/test/{filename}",
        "filename": filename,
    }


@router.get("/image/test/{filename}")
def get_test_image_file(filename: str):
    """读取测试生成图片。"""
    safe = Path(filename).name
    path = _TEST_IMAGE_DIR / safe
    if not path.is_file():
        raise HTTPException(404, detail="测试图片不存在或已过期")
    return FileResponse(path, media_type="image/png", filename=safe)


@router.post("/image/detect-sd")
async def detect_sd():
    """检测本地 SD WebUI 是否可用，返回模型列表。"""
    mgr = get_image_gen_manager()
    result = await mgr.detect_sd(force=True)
    # 同步持久化配置中的 sd_detected 状态（不需要，仅内存缓存）
    return {"ok": True, **result}
