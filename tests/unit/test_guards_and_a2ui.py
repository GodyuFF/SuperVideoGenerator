"""单元测试：守卫、A2UI 确认管理器、领域模型默认值。"""

import pytest

from core.a2ui.manager import ConfirmationManager, ConfirmationRejectedError, ConfirmationTimeoutError
from core.a2ui.schemas import A2UIConfirmationResponse
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
  """默认配置应为费用确认模式 + 动态图片风格。"""
  from core.models.entities import ProjectConfig

  cfg = ProjectConfig()
  assert cfg.generation.mode == GenerationMode.COST_CONFIRM
  assert cfg.style.mode == VideoStyleMode.DYNAMIC_IMAGE


def test_script_editable_only_draft_planned():
  """仅 draft/planned 状态剧本可编辑。"""
  draft = Script(project_id="p1", title="t", status=ScriptStatus.DRAFT)
  planned = Script(project_id="p1", title="t", status=ScriptStatus.PLANNED)
  executing = Script(project_id="p1", title="t", status=ScriptStatus.EXECUTING)

  assert ScriptEditGuard.is_editable(draft)
  assert ScriptEditGuard.is_editable(planned)
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


@pytest.mark.asyncio
async def test_wait_for_video_gen_auto_skips():
  """自动生成模式应跳过视频生成 A2UI 确认。"""
  emitter = EventEmitter()
  mgr = ConfirmationManager(emitter)
  result = await mgr.wait_for_video_gen("step_1", 3, 0.45, mode="auto")
  assert result is True
  assert len(mgr._pending) == 0


@pytest.mark.asyncio
async def test_wait_for_video_gen_cost_confirm():
  """费用确认模式应等待用户 A2UI 同意。"""
  emitter = EventEmitter()
  events = []

  async def capture(e):
    events.append(e)

  emitter.subscribe(capture)
  mgr = ConfirmationManager(emitter, default_timeout=5.0)

  async def approve():
    import asyncio

    await asyncio.sleep(0.05)
    for e in events:
      if e.get("type") == "a2ui_confirmation_required":
        mgr.resolve(
          A2UIConfirmationResponse(
            confirmation_id=e["confirmation_id"], approved=True
          )
        )
        break

  import asyncio

  task = asyncio.create_task(approve())
  result = await mgr.wait_for_video_gen("step_1", 3, 0.45, mode="cost_confirm")
  await task
  assert result is True


@pytest.mark.asyncio
async def test_wait_for_video_gen_rejected():
  """费用确认模式下用户拒绝应抛出 ConfirmationRejectedError。"""
  emitter = EventEmitter()
  events = []

  async def capture(e):
    events.append(e)

  emitter.subscribe(capture)
  mgr = ConfirmationManager(emitter, default_timeout=5.0)

  async def reject():
    import asyncio

    await asyncio.sleep(0.05)
    for e in events:
      if e.get("type") == "a2ui_confirmation_required":
        mgr.resolve(
          A2UIConfirmationResponse(
            confirmation_id=e["confirmation_id"], approved=False
          )
        )
        break

  import asyncio

  task = asyncio.create_task(reject())
  with pytest.raises(ConfirmationRejectedError):
    await mgr.wait_for_video_gen("step_1", 3, 0.45, mode="cost_confirm")
  await task
