"""单元测试：守卫、A2UI 确认管理器、领域模型默认值。"""

import pytest

from core.llm.a2ui.manager import ConfirmationManager, ConfirmationRejectedError, ConfirmationTimeoutError
from core.llm.a2ui.schemas import A2UIConfirmationResponse
from core.events.emitter import EventEmitter
from core.guards.reference import ReferenceGuard, ReferenceGuardError, ScriptEditGuard, ScriptEditGuardError
from core.models.entities import (
  AssetReference,
  AssetScope,
  AssetStatus,
  GenerationMode,
  Project,
  RelationType,
  Script,
  ScriptStatus,
  TextAsset,
  TextAssetType,
  VideoStyleMode,
)
from core.store.memory import MemoryStore


def test_new_id_prefix():
  """ID 生成应包含类型前缀。"""
  from core.models.entities import new_id

  assert new_id("proj").startswith("proj_")


def test_project_config_defaults():
  """默认配置应为自动模式 + 动态图片风格。"""
  from core.models.entities import ProjectConfig

  cfg = ProjectConfig()
  assert cfg.generation.mode == GenerationMode.AUTO
  assert cfg.style.mode == VideoStyleMode.STORYBOOK


def test_script_editable_only_when_not_executing():
  """executing 禁止编辑；draft/planned/completed/failed 允许。"""
  draft = Script(project_id="p1", title="t", status=ScriptStatus.DRAFT)
  planned = Script(project_id="p1", title="t", status=ScriptStatus.PLANNED)
  completed = Script(project_id="p1", title="t", status=ScriptStatus.COMPLETED)
  executing = Script(project_id="p1", title="t", status=ScriptStatus.EXECUTING)

  assert ScriptEditGuard.is_editable(draft)
  assert ScriptEditGuard.is_editable(planned)
  assert ScriptEditGuard.is_editable(completed)
  assert not ScriptEditGuard.is_editable(executing)

  with pytest.raises(ScriptEditGuardError):
    ScriptEditGuard.assert_editable(executing)


def test_reference_guard_blocks_delete():
  """被引用的资产不可删除。"""
  store = MemoryStore()
  guard = ReferenceGuard(store)
  asset = TextAsset(
    project_id="proj_1",
    script_id="script_1",
    type=TextAssetType.PLOT,
    name="plot",
  )
  store.add_text_asset(asset)
  ref = AssetReference(
    source_id="shot_1",
    target_id=asset.id,
    relation=RelationType.USES,
    script_id="script_1",
  )
  store.add_reference(ref)

  ok, refs = guard.can_delete(asset.id)
  assert not ok
  assert len(refs) == 1

  with pytest.raises(ReferenceGuardError):
    guard.assert_can_delete(asset.id)


@pytest.mark.asyncio
async def test_confirmation_manager_resolve():
  """A2UI 确认：用户同意后 Future 应正确 resolve。"""
  emitter = EventEmitter()
  events = []

  async def capture(e):
    events.append(e)

  emitter.subscribe(capture)
  mgr = ConfirmationManager(emitter, default_timeout=5.0)

  async def approve():
    import asyncio

    await asyncio.sleep(0.05)
    conf_id = events[0]["confirmation_id"]
    mgr.resolve(
      A2UIConfirmationResponse(confirmation_id=conf_id, approved=True)
    )

  import asyncio

  approve_task = asyncio.create_task(approve())
  response = await mgr.request(
    kind="generic",
    title="测试确认",
    description="描述",
    timeout=5.0,
  )
  await approve_task
  assert response.approved


@pytest.mark.asyncio
async def test_a2ui_persisted_to_sqlite(tmp_path):
    from core.conversation.sqlite_store import ConversationSqliteStore

    sqlite = ConversationSqliteStore(db_path=tmp_path / "a2ui.db")
    emitter = EventEmitter()
    events = []

    async def capture(e):
        events.append(e)

    emitter.subscribe(capture)
    mgr = ConfirmationManager(emitter, default_timeout=5.0, sqlite_store=sqlite)

    async def approve():
        import asyncio

        await asyncio.sleep(0.05)
        conf_id = events[0]["confirmation_id"]
        mgr.resolve(
            A2UIConfirmationResponse(
                confirmation_id=conf_id,
                approved=True,
                values={"theme": "科幻"},
            )
        )

    import asyncio

    approve_task = asyncio.create_task(approve())
    await mgr.request(
        kind="generic",
        title="测试确认",
        description="描述",
        timeout=5.0,
        conversation_id="conv_sqlite",
    )
    await approve_task
    records = sqlite.list_a2ui("conv_sqlite")
    assert len(records) == 1
    assert records[0].approved is True


@pytest.mark.asyncio
async def test_confirmation_manager_has_pending():
    """has_pending 应反映未 resolve 的确认。"""
    emitter = EventEmitter()
    mgr = ConfirmationManager(emitter, default_timeout=5.0)

    async def approve_later():
        import asyncio

        await asyncio.sleep(0.05)
        conf_id = next(iter(mgr._pending))
        mgr.resolve(
            A2UIConfirmationResponse(confirmation_id=conf_id, approved=True)
        )

    import asyncio

    task = asyncio.create_task(approve_later())
    request_task = asyncio.create_task(
        mgr.request(kind="generic", title="pending 测试", timeout=5.0)
    )
    await asyncio.sleep(0.02)
    assert mgr.has_pending()
    await request_task
    await task
    assert not mgr.has_pending()


@pytest.mark.asyncio
async def test_confirmation_emits_execution_paused_resumed():
    """确认请求应推送 execution_paused / execution_resumed。"""
    emitter = EventEmitter()
    events: list[dict] = []

    async def capture(e: dict) -> None:
        events.append(e)

    emitter.subscribe(capture)
    mgr = ConfirmationManager(emitter, default_timeout=5.0)

    async def approve():
        import asyncio

        await asyncio.sleep(0.05)
        conf_id = next(iter(mgr._pending))
        mgr.resolve(
            A2UIConfirmationResponse(confirmation_id=conf_id, approved=True)
        )

    import asyncio

    task = asyncio.create_task(approve())
    await mgr.request(
        kind="generic",
        title="事件测试",
        timeout=5.0,
        conversation_id="conv_evt",
    )
    await task
    types = [e.get("type") for e in events]
    assert "execution_paused" in types
    assert "execution_resumed" in types


@pytest.mark.asyncio
async def test_confirmation_waits_indefinitely_until_user_responds():
    """默认无超时时，确认应持续挂起直至用户响应。"""
    import asyncio

    emitter = EventEmitter()
    mgr = ConfirmationManager(emitter, default_timeout=None)

    async def approve_later():
        await asyncio.sleep(0.15)
        conf_id = next(iter(mgr._pending))
        mgr.resolve(
            A2UIConfirmationResponse(confirmation_id=conf_id, approved=True)
        )

    task = asyncio.create_task(approve_later())
    request_task = asyncio.create_task(
        mgr.request(kind="generic", title="无限等待测试")
    )
    await asyncio.sleep(0.05)
    assert mgr.has_pending()
    response = await request_task
    await task
    assert response.approved
    assert not mgr.has_pending()


@pytest.mark.asyncio
async def test_confirmation_timeout_emits_expired_and_resolve_reason():
  """显式超时应推送 a2ui_confirmation_expired，迟到 resolve 返回 expired。"""
  import asyncio

  emitter = EventEmitter()
  events: list[dict] = []

  async def capture(e: dict) -> None:
    events.append(e)

  emitter.subscribe(capture)
  mgr = ConfirmationManager(emitter, default_timeout=None)

  with pytest.raises(ConfirmationTimeoutError) as exc_info:
    await mgr.request(kind="generic", title="超时测试", timeout=0.05)

  assert "用户确认超时" in str(exc_info.value)
  types = [e.get("type") for e in events]
  assert "a2ui_confirmation_expired" in types
  assert "execution_resumed" in types
  conf_id = exc_info.value.confirmation_id
  result = mgr.resolve(
    A2UIConfirmationResponse(confirmation_id=conf_id, approved=True)
  )
  assert result.resolved is False
  assert result.reason == "expired"


@pytest.mark.asyncio
async def test_confirmation_timeout_persists_expired_to_sqlite(tmp_path):
  """超时后 SQLite 记录应为 expired（intent=expired）。"""
  from core.conversation.sqlite_store import ConversationSqliteStore
  from core.conversation.timeline import _a2ui_timeline_item

  sqlite = ConversationSqliteStore(db_path=tmp_path / "a2ui_expire.db")
  emitter = EventEmitter()
  mgr = ConfirmationManager(emitter, default_timeout=None, sqlite_store=sqlite)

  with pytest.raises(ConfirmationTimeoutError):
    await mgr.request(
      kind="generic",
      title="超时落库",
      timeout=0.05,
      conversation_id="conv_expire",
    )

  records = sqlite.list_a2ui("conv_expire")
  assert len(records) == 1
  assert records[0].resolved_at is not None
  assert records[0].approved is False
  item = _a2ui_timeline_item(records[0])
  assert item["status"] == "expired"


def test_parse_a2ui_default_timeout():
  """环境变量解析：空/0/none → None；正数 → float。"""
  from apps.api.state import parse_a2ui_default_timeout

  assert parse_a2ui_default_timeout("") is None
  assert parse_a2ui_default_timeout("none") is None
  assert parse_a2ui_default_timeout("0") is None
  assert parse_a2ui_default_timeout("300") == 300.0
  assert parse_a2ui_default_timeout("1.5") == 1.5


@pytest.mark.asyncio
async def test_confirmation_rejected():
  """A2UI 确认：用户拒绝时 approved 为 False。"""
  emitter = EventEmitter()
  mgr = ConfirmationManager(emitter, default_timeout=5.0)

  async def reject():
    import asyncio

    await asyncio.sleep(0.02)
    conf_id = next(iter(mgr._pending))
    mgr.resolve(
      A2UIConfirmationResponse(confirmation_id=conf_id, approved=False)
    )

  import asyncio

  task = asyncio.create_task(reject())
  response = await mgr.request(kind="generic", title="测试", timeout=5.0)
  await task
  assert not response.approved

