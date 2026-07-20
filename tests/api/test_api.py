"""API 集成测试：REST 端点与健康检查。"""

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app
from core.models.entities import GenerationMode, VideoStyleMode
from tests.support.chat_wait import wait_for_chat_idle


@pytest.mark.asyncio
async def test_health():
  """健康检查应返回 ok。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_project_and_script():
  """应能创建项目、剧本并更新配置。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.post("/api/projects", json={"title": "API 测试项目"})
    assert r.status_code == 200
    project = r.json()
    pid = project["id"]

    r = await client.post(
      f"/api/projects/{pid}/scripts",
      json={"title": "第一集", "duration_sec": 90},
    )
    assert r.status_code == 200
    script = r.json()
    assert script["title"] == "第一集"

    r = await client.patch(
      f"/api/projects/{pid}/config",
      json={
        "generation_mode": GenerationMode.AUTO.value,
      },
    )
    assert r.status_code == 200
    assert r.json()["generation"]["mode"] == "auto"


@pytest.mark.asyncio
async def test_get_plan_empty_before_chat():
    """未对话时 GET plan 应返回 200 空计划，而非 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "空计划测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        r = await client.get(f"/api/projects/{pid}/scripts/{sid}/plan")
        assert r.status_code == 200
        body = r.json()
        assert body.get("steps") == []
        assert body.get("goal", "") == ""


@pytest.mark.asyncio
async def test_chat_rejects_style_change_when_locked():
  """风格锁定后 chat 传入不同 style_mode 应被拒绝。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.post("/api/projects", json={"title": "锁定测试"})
    pid = r.json()["id"]
    r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
    sid = r.json()["id"]

    r = await client.post(
      f"/api/projects/{pid}/scripts/{sid}/chat",
      json={
        "message": "第一段剧本",
        "style_mode": VideoStyleMode.STORYBOOK.value,
        "generation_mode": GenerationMode.AUTO.value,
      },
    )
    assert r.status_code == 202
    await wait_for_chat_idle(client, pid, sid)

    r = await client.post(
      f"/api/projects/{pid}/scripts/{sid}/chat",
      json={
        "message": "尝试改风格",
        "style_mode": VideoStyleMode.AI_VIDEO.value,
      },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_conversation_api_flow():
    """创建对话 → 带 id chat → 列表 → 拉消息。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "会话测试"})
        pid = r.json()["id"]
        r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
        sid = r.json()["id"]

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/conversations",
            json={"title": "测试对话"},
        )
        assert r.status_code == 200
        conv_id = r.json()["conversation_id"]

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/chat",
            json={
                "message": "制作一段60秒短片",
                "conversation_id": conv_id,
                "generation_mode": GenerationMode.AUTO.value,
                "style_mode": VideoStyleMode.STORYBOOK.value,
            },
        )
        assert r.status_code == 202
        assert r.json()["conversation_id"] == conv_id
        await wait_for_chat_idle(client, pid, sid)

        r = await client.get(f"/api/projects/{pid}/conversations?script_id={sid}")
        assert r.status_code == 200
        items = r.json()
        assert any(c["id"] == conv_id for c in items)

        r = await client.get(f"/api/projects/{pid}/conversations/{conv_id}/messages")
        assert r.status_code == 200
        msgs = r.json()
        assert any(m["role"] == "user" for m in msgs)

        r = await client.get(
            f"/api/projects/{pid}/conversations/{conv_id}/messages?view=full"
        )
        assert r.status_code == 200
        full = r.json()
        assert full["conversation_id"] == conv_id
        assert isinstance(full["timeline"], list)
        assert any(t.get("type") == "user" for t in full["timeline"])

        # 跨 project 拒绝
        r = await client.post("/api/projects", json={"title": "其他项目"})
        other_pid = r.json()["id"]
        r = await client.get(f"/api/projects/{other_pid}/conversations/{conv_id}/messages")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_chat_drives_full_pipeline():
  """对话 API：超级视频大师自动 Plan + Execute 应完成，并绑定风格。"""
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
    r = await client.post("/api/projects", json={"title": "对话测试"})
    pid = r.json()["id"]
    r = await client.post(f"/api/projects/{pid}/scripts", json={"title": "S1"})
    sid = r.json()["id"]

    r = await client.post(
      f"/api/projects/{pid}/scripts/{sid}/chat",
      json={
        "message": "制作一段60秒都市情感短片",
        "generation_mode": GenerationMode.AUTO.value,
        "style_mode": VideoStyleMode.STORYBOOK.value,
      },
    )
    assert r.status_code == 202
    await wait_for_chat_idle(client, pid, sid)

    r = await client.get(f"/api/projects/{pid}/scripts/{sid}")
    assert r.status_code == 200
    script = r.json()
    assert script["status"] == "completed"
    assert script["style_locked"] is True
    assert script["style_mode"] == "storybook"

    r = await client.get(f"/api/projects/{pid}/scripts/{sid}/plan")
    assert r.status_code == 200
    plan = r.json()
    assert len(plan["steps"]) >= 4

    r = await client.get(f"/api/projects/{pid}/scripts/{sid}/assets")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_patch_text_asset_updates_content():
    """PATCH 图文资产应更新 content 并设置 user_edited。"""
    from core.llm.agent.script_assets import create_text_asset_for_action

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "PATCH 测试"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "S1", "duration_sec": 60},
        )
        sid = r.json()["id"]

        from apps.api.state import state

        char = create_text_asset_for_action(
            state.store,
            action="create_character",
            project_id=pid,
            script_id=sid,
            asset_name="测试角色",
            content={
                "summary": "测试",
                "description": "测试角色描述" * 10,
                "prompt_hint": "侧光",
                "visual_style": "未指定",
                "color_palette": "未指定",
                "role": "主角",
                "personality": "未指定",
                "age_range": "未指定",
                "gender": "未指定",
                "costume": "未指定",
                "distinctive_features": "未指定",
                "ethnicity": "未指定",
                "body_type": "未指定",
                "height": "未指定",
                "build": "未指定",
                "hair_style": "未指定",
                "hair_color": "未指定",
                "eye_color": "未指定",
                "facial_features": "未指定",
                "default_expression": "未指定",
                "default_pose": "未指定",
                "accessories": "未指定",
            },
            observation="",
        ).asset

        r = await client.patch(
            f"/api/projects/{pid}/assets/{char.id}",
            json={
                "content": {"costume": "红色风衣", "prompt_locked": False},
                "force_recompose_prompt": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["user_edited"] is True
        assert body["content"]["costume"] == "红色风衣"
        assert body["content"]["image_prompt"]
        assert "红色风衣" in body["content"]["image_prompt"]


@pytest.mark.asyncio
async def test_patch_text_asset_updates_variant_prompt():
    """PATCH 图文资产应持久化变体 variant_prompt 并重算变体 image_prompt。"""
    from core.llm.agent.script_assets import create_text_asset_for_action
    from core.models.image_text_asset import merge_incoming_variants, parse_image_variants

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "变体 PATCH"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "S1", "duration_sec": 60},
        )
        sid = r.json()["id"]

        from apps.api.state import state

        char = create_text_asset_for_action(
            state.store,
            action="create_character",
            project_id=pid,
            script_id=sid,
            asset_name="变体角色",
            content=merge_incoming_variants(
                {
                    "summary": "测试",
                    "description": "一位穿蓝色外套的年轻女性，短发，站在城市街头",
                    "prompt_hint": "侧光",
                    "visual_style": "未指定",
                    "color_palette": "未指定",
                    "role": "主角",
                    "personality": "开朗",
                    "age_range": "20岁",
                    "gender": "女",
                    "costume": "蓝色外套",
                    "distinctive_features": "短发",
                    "ethnicity": "未指定",
                    "body_type": "未指定",
                    "height": "未指定",
                    "build": "未指定",
                    "hair_style": "短发",
                    "hair_color": "未指定",
                    "eye_color": "未指定",
                    "facial_features": "未指定",
                    "default_expression": "未指定",
                    "default_pose": "未指定",
                    "accessories": "未指定",
                },
                [{"kind": "expression", "label": "微笑", "variant_prompt": "温和微笑"}],
            ),
            observation="",
        ).asset
        expr = [v for v in parse_image_variants(char.content) if v.kind == "expression"][0]

        r = await client.patch(
            f"/api/projects/{pid}/assets/{char.id}",
            json={
                "content": {
                    "image_variants": [
                        {
                            "id": expr.id,
                            "kind": "expression",
                            "label": "微笑",
                            "variant_prompt": "开怀大笑，眼睛弯成月牙",
                        }
                    ],
                    "prompt_locked": True,
                },
                "prompt_locked": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        variants = parse_image_variants(body["content"])
        updated = [v for v in variants if v.id == expr.id][0]
        assert updated.variant_prompt == "开怀大笑，眼睛弯成月牙"
        assert updated.image_prompt
        assert "开怀大笑" in updated.image_prompt


@pytest.mark.asyncio
async def test_manual_asset_crud_and_script_patch():
    """用户手动创建/删除资产与 PATCH 剧本正文。"""
    from core.models.entities import ScriptStatus

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/projects", json={"title": "手动 CRUD"})
        pid = r.json()["id"]
        r = await client.post(
            f"/api/projects/{pid}/scripts",
            json={"title": "S1", "duration_sec": 60},
        )
        sid = r.json()["id"]

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/assets",
            json={"type": "plot", "name": "段落1", "content": {"text": "剧情正文"}},
        )
        assert r.status_code == 200
        plot_id = r.json()["id"]

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/assets",
            json={
                "type": "frame",
                "name": "手动画面",
                "content": {
                    "summary": "城市黎明",
                    "description": "高空俯瞰清晨城市天际线，薄雾笼罩楼宇，暖色晨光从东侧云层渗出照亮轮廓。" * 2,
                },
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["type"] == "frame"
        frame_id = r.json()["id"]

        r = await client.patch(
            f"/api/projects/{pid}/scripts/{sid}",
            json={"content_md": "# 标题\n\n正文", "title": "新名"},
        )
        assert r.status_code == 200
        assert r.json()["content_md"].startswith("# 标题")

        from apps.api.state import state

        script = state.store.get_script(sid)
        assert script is not None
        script.status = ScriptStatus.EXECUTING

        r = await client.post(
            f"/api/projects/{pid}/scripts/{sid}/assets",
            json={"type": "plot", "name": "blocked"},
        )
        assert r.status_code == 403

        script.status = ScriptStatus.COMPLETED

        r = await client.delete(f"/api/projects/{pid}/scripts/{sid}/assets/{plot_id}")
        assert r.status_code == 200

        r = await client.delete(f"/api/projects/{pid}/scripts/{sid}/assets/{frame_id}")
        assert r.status_code == 200
