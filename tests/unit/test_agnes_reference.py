"""Agnes reference 生图客户端测试（单图薄封装）。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm.tools.image.agnes_client import (
    AgnesImageGenerationError,
    generate_image_with_reference_async,
)
from core.llm.tools.image.settings import ImageGenSettings, reset_image_gen_settings


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_image_gen_settings()
    yield
    reset_image_gen_settings()


@pytest.mark.asyncio
async def test_reference_generation_sends_image_array_in_extra_body():
    settings = ImageGenSettings(
        api_key="test-key",
        reference_enabled=True,
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"url": "https://cdn.test/out.png"}]}

    with patch("core.llm.tools.image.agnes_client.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.post = AsyncMock(return_value=mock_resp)
        client_cls.return_value = client

        url = await generate_image_with_reference_async(
            "same character smiling",
            "https://images.test/ref.png",
            settings=settings,
        )

    assert url == "https://cdn.test/out.png"
    call_kwargs = client.post.call_args.kwargs
    payload = call_kwargs["json"]
    assert payload["extra_body"]["image"] == ["https://images.test/ref.png"]


@pytest.mark.asyncio
async def test_reference_disabled_raises():
    settings = ImageGenSettings(api_key="k", reference_enabled=False)
    with pytest.raises(AgnesImageGenerationError, match="未启用"):
        await generate_image_with_reference_async("p", "https://x/y.png", settings=settings)
