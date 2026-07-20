"""OpenAI 生图 client payload 测试。"""

from core.llm.tools.image.openai_image_client import build_openai_image_payload_preview
from core.llm.tools.image.settings import ImageGenSettings


def test_openai_image_payload_preview():
    settings = ImageGenSettings(provider="openai", model="gpt-image-1", default_size="1024x768")
    payload = build_openai_image_payload_preview("a cat", settings)
    assert payload["model"] == "gpt-image-1"
    assert payload["prompt"] == "a cat"
    assert payload["size"] == "1024x768"
