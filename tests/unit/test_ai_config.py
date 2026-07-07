"""AiConfigManager 与 ai_config.json 持久化单元测试。"""

import json

from core.llm.ai_config import AiConfigManager
from core.llm.ai_config_store import load_ai_config
from core.llm.client.settings import LLMConfigManager
from core.llm.tools.image.settings import ImageGenConfigManager, reset_image_gen_settings


def test_ai_config_public_sections():
    reset_image_gen_settings()
    mgr = AiConfigManager(LLMConfigManager(), ImageGenConfigManager())
    public = mgr.get_public_config()
    assert set(public.keys()) == {"llm", "image", "video", "tts", "export"}
    assert public["image"]["provider"] == "agnes"
    assert "pipeline" in public["image"]
    assert "llm_active" in public["llm"]


def test_ai_config_update_image_api_and_pipeline(tmp_path, monkeypatch):
    reset_image_gen_settings()
    config_path = tmp_path / "ai_config.json"
    monkeypatch.setattr("core.llm.ai_config.DEFAULT_PATH", config_path)
    llm = LLMConfigManager()
    image = ImageGenConfigManager()
    mgr = AiConfigManager(llm, image, path=config_path)
    updated = mgr.update(
        image={
            "model": "agnes-image-2.1-flash",
            "default_size": "768x1024",
            "pipeline": {"source_mode": "user_choice", "comic_preset": "ink"},
        }
    )
    assert updated["image"]["model"] == "agnes-image-2.1-flash"
    assert updated["image"]["default_size"] == "768x1024"
    assert updated["image"]["pipeline"]["source_mode"] == "user_choice"
    assert updated["image"]["pipeline"]["comic_preset"] == "ink"


def test_ai_config_persist_and_reload(tmp_path, monkeypatch):
    reset_image_gen_settings()
    config_path = tmp_path / "ai_config.json"
    monkeypatch.setattr("core.llm.ai_config.DEFAULT_PATH", config_path)

    mgr1 = AiConfigManager(LLMConfigManager(), ImageGenConfigManager(), path=config_path)
    mgr1.update(
        llm={
            "provider": "deepseek",
            "api_key": "sk-test-key",
            "model": "deepseek-chat",
            "temperature": 0.5,
        }
    )
    assert config_path.is_file()
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["llm"]["api_key"] == "sk-test-key"
    assert saved["llm"]["provider"] == "deepseek"

    mgr2 = AiConfigManager(LLMConfigManager(), ImageGenConfigManager(), path=config_path)
    assert mgr2.llm.resolved_api_key() == "sk-test-key"
    assert mgr2.llm.get_settings().provider == "deepseek"
    assert mgr2.llm.get_settings().temperature == 0.5
    public = mgr2.get_public_config()
    assert public["llm"]["has_api_key"] is True
    assert public["llm"]["model"] == "deepseek-chat"


def test_ai_config_show_react_details_persist(tmp_path, monkeypatch):
    reset_image_gen_settings()
    config_path = tmp_path / "ai_config.json"
    monkeypatch.setattr("core.llm.ai_config.DEFAULT_PATH", config_path)
    mgr = AiConfigManager(LLMConfigManager(), ImageGenConfigManager(), path=config_path)
    updated = mgr.update(llm={"show_react_details": False})
    assert updated["llm"]["show_react_details"] is False
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["llm"]["show_react_details"] is False

    mgr2 = AiConfigManager(LLMConfigManager(), ImageGenConfigManager(), path=config_path)
    assert mgr2.llm.get_settings().show_react_details is False


def test_load_ai_config_missing_file(tmp_path):
    assert load_ai_config(tmp_path / "missing.json") == {}
