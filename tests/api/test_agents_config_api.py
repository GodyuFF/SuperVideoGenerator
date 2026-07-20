"""Agent 配置 API 集成测试。"""



from fastapi.testclient import TestClient



from apps.api.main import app



client = TestClient(app)





def test_get_agents_config_includes_extended_fields():

    r = client.get("/api/agents/config")

    assert r.status_code == 200

    data = r.json()

    assert "custom_profiles" in data

    assert "style_modes" in data

    assert "prompt_content" in data

    assert "tool_overrides" in data

    default_profile = next(p for p in data["available_profiles"] if p["id"] == "default")

    assert default_profile["editable"] is False

    assert default_profile["deletable"] is False





def test_list_agents_includes_master():

    r = client.get("/api/agents")

    assert r.status_code == 200

    names = [a["name"] for a in r.json()["agents"]]

    assert "super_video_master" in names





def test_style_modes_api():

    r = client.get("/api/style-modes")

    assert r.status_code == 200

    ids = {m["id"] for m in r.json()["style_modes"]}

    assert "storybook" in ids

    assert "ai_video" in ids

    assert "frame_i2v" in ids

    assert "dynamic_comic" not in ids

    assert "marketing_video" not in ids


def test_style_modes_api_excludes_removed_legacy_entries(tmp_path, monkeypatch):
    """registry 残留 dynamic_comic / marketing_video 时 API 仍只返回三种内置风格。"""
    import json

    from core.llm.agent.config_manager import set_agent_config_manager

    agents_root = tmp_path / "agents"
    agents_root.mkdir(parents=True)
    (agents_root / "registry.json").write_text(
        json.dumps(
            {
                "style_modes": [
                    {
                        "id": "dynamic_comic",
                        "label": "动态漫画",
                        "default_prompt_profile": "dynamic_comic",
                        "builtin": True,
                    },
                    {
                        "id": "marketing_video",
                        "label": "营销视频",
                        "default_prompt_profile": "marketing_video",
                        "builtin": False,
                    },
                ],
                "custom_profiles": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SVG_AGENTS_ROOT", str(agents_root))
    set_agent_config_manager(None)

    r = client.get("/api/style-modes")
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["style_modes"]}
    assert ids == {"storybook", "ai_video", "frame_i2v"}

    cfg = client.get("/api/agents/config")
    assert cfg.status_code == 200
    assert cfg.json()["style_modes"] == []

    set_agent_config_manager(None)





def test_tools_api():
    r = client.get("/api/tools")
    assert r.status_code == 200
    body = r.json()
    assert "super_video_master" in body["agents"]
    assert "governance" in body
    assert body["governance"]["edit_timeline_write_agent"] == "editing_agent"
    assert "catalog" in body
    sync_tool = next(
        (t for t in body["catalog"] if t.get("action") == "sync_actual_assets"),
        None,
    )
    assert sync_tool is not None
    assert sync_tool.get("may_write_edit_timeline") is False
    assert sync_tool.get("input_schema", {}).get("type") == "object"
    assert sync_tool.get("output_schema", {}).get("type") == "object"





def test_patch_prompt_content_roundtrip():

    r = client.patch(

        "/api/agents/config",

        json={

            "prompt_content": {

                "script_agent": {

                    "storybook": {"role_prompt": "API 测试 role"},

                }

            }

        },

    )

    assert r.status_code == 200

    pr = client.get("/api/agents/script_agent/prompt?profile=storybook")

    assert pr.status_code == 200

    assert pr.json()["role_prompt"] == "API 测试 role"





def test_patch_default_profile_rejected():

    r = client.patch(

        "/api/agents/config",

        json={

            "prompt_content": {

                "script_agent": {

                    "default": {"role_prompt": "禁止写入"},

                }

            }

        },

    )

    assert r.status_code == 400





def test_builtin_style_profiles_not_deletable():

    r = client.get("/api/agents/config")

    assert r.status_code == 200

    for pid in ("storybook", "ai_video", "frame_i2v"):

        profile = next(p for p in r.json()["available_profiles"] if p["id"] == pid)

        assert profile["deletable"] is False

        assert profile["restorable"] is True





def test_restore_builtin_profile_api():

    profile_id = "storybook"

    client.patch(

        "/api/agents/config",

        json={

            "prompt_content": {

                "script_agent": {

                    profile_id: {"role_prompt": "待恢复"},

                }

            }

        },

    )

    r = client.post(f"/api/agents/profiles/{profile_id}/restore")

    assert r.status_code == 200

    pr = client.get(f"/api/agents/script_agent/prompt?profile={profile_id}")

    assert pr.status_code == 200

    assert pr.json()["source"]["role_prompt"] == "file"





def test_restore_custom_profile_rejected():

    r = client.post("/api/agents/profiles/marketing_video/restore")

    assert r.status_code == 400


