"""storyboard create_frames 与子镜 frame 关联测试。"""



import pytest



from core.llm.agent.llm_action import (

    _assert_sub_shots_have_frames,

    _create_frame_assets_from_data,

    apply_action_result,

    parse_shots_from_data,

)

from core.llm.agent.react_core import AgentRunContext

from core.models.entities import (

    AssetScope,

    Project,

    Script,

    TextAsset,

    TextAssetType,

    VideoStyleMode,

)

from core.store.memory import MemoryStore

from tests.support.shot_fixtures import make_shot, shot_design_payload





def test_create_frames_links_shot_and_frame_asset():

    store = MemoryStore()

    project = Project(title="p")

    store.add_project(project)

    script = Script(project_id=project.id, title="s")

    store.add_script(script)

    scene = TextAsset(

        project_id=project.id,

        type=TextAssetType.SCENE,

        scope=AssetScope.PROJECT_SHARED,

        name="空镜",

        content={"description": "城市夜景背景板描述足够长用于测试。" * 2},

        source_script_id=script.id,

    )

    store.add_text_asset(scene)



    shot = make_shot(

        order=0,

        text="旁白",

        duration_ms=3000,

    )

    sub_id = shot.sub_shots[0].id

    shot.sub_shots[0].element_refs = {"scene": [scene.id]}

    ctx = AgentRunContext(

        task_brief="",

        work_context={"project_id": project.id, "script_id": script.id},

        script_id=script.id,

        step_id="",

        agent_name="storyboard_agent",

    )

    created, updated, links = _create_frame_assets_from_data(

        store,

        ctx,

        [

            {

                "shot_id": shot.id,

                "sub_shot_id": sub_id,

                "image_prompt": "纯空镜，无人物",

                "element_refs": {"scene": [scene.id]},

            }

        ],

        [shot],

    )

    assert len(created) == 1

    assert created[0].type == TextAssetType.FRAME

    assert updated[0].sub_shots[0].images

    assert updated[0].sub_shots[0].images[0].frame_asset_id == created[0].id

    assert created[0].content.get("shot_id") == shot.id

    assert links[0]["sub_shot_id"] == sub_id





def test_create_frames_fallback_sub_shot_index_on_bad_id():
    """自造 sub_shot_id 时可用 sub_shot_index 回退定位子镜。"""
    store = MemoryStore()
    project = Project(title="p")
    store.add_project(project)
    script = Script(project_id=project.id, title="s")
    store.add_script(script)
    shot = make_shot(order=0, text="旁白", duration_ms=3000)
    ctx = AgentRunContext(
        task_brief="",
        work_context={"project_id": project.id, "script_id": script.id},
        script_id=script.id,
        step_id="",
        agent_name="storyboard_agent",
    )
    created, updated, links = _create_frame_assets_from_data(
        store,
        ctx,
        [
            {
                "order": 0,
                "sub_shot_id": "shot_0_sub_0",
                "sub_shot_index": 0,
                "image_prompt": "空镜",
                "element_refs": {},
            }
        ],
        [shot],
    )
    assert len(created) == 1
    assert links[0]["sub_shot_id"] == shot.sub_shots[0].id
    assert updated[0].sub_shots[0].images[0].frame_asset_id == created[0].id


def test_create_frames_requires_sub_shot_id():

    """缺 sub_shot_id 时应报错，禁止静默落到首个子镜。"""

    store = MemoryStore()

    project = Project(title="p")

    store.add_project(project)

    script = Script(project_id=project.id, title="s")

    store.add_script(script)

    shot = make_shot(order=0, text="旁白", duration_ms=3000)

    ctx = AgentRunContext(

        task_brief="",

        work_context={"project_id": project.id, "script_id": script.id},

        script_id=script.id,

        step_id="",

        agent_name="storyboard_agent",

    )

    with pytest.raises(ValueError, match="sub_shot_id"):

        _create_frame_assets_from_data(

            store,

            ctx,

            [{"shot_id": shot.id, "image_prompt": "空镜"}],

            [shot],

        )





def test_apply_create_frames_action():

    store = MemoryStore()

    project = Project(title="p")

    store.add_project(project)

    script = Script(project_id=project.id, title="s")

    store.add_script(script)

    shot = make_shot(order=0, text="旁白", duration_ms=3000)

    sub_id = shot.sub_shots[0].id

    ctx = AgentRunContext(

        task_brief="",

        work_context={

            "project_id": project.id,

            "script_id": script.id,

            "_pending_shots": [shot],

        },

        script_id=script.id,

        step_id="",

        agent_name="storyboard_agent",

    )

    scene = TextAsset(

        project_id=project.id,

        type=TextAssetType.SCENE,

        scope=AssetScope.PROJECT_SHARED,

        name="空镜",

        content={"description": "背景描述足够长用于测试验证。" * 2},

        source_script_id=script.id,

    )

    store.add_text_asset(scene)



    obs = apply_action_result(

        store,

        "storyboard_agent",

        "create_frames",

        ctx,

        {

            "observation": "创建剧本画面",

            "frames": [

                {

                    "shot_id": shot.id,

                    "sub_shot_id": sub_id,

                    "image_prompt": "空镜镜头",

                    "element_refs": {"scene": [scene.id]},

                }

            ],

        },

    )

    assert "剧本画面" in obs or "frame" in obs.lower()

    pending = ctx.work_context["_pending_shots"]

    assert pending[0].sub_shots[0].images

    assert pending[0].sub_shots[0].images[0].frame_asset_id

    assert ctx.work_context.get("_frame_links")





def test_multi_sub_shot_requires_multiple_frames():

    """两子镜须分别 create_frames，persist 缺一则拒绝。"""

    store = MemoryStore()

    project = Project(title="p")

    store.add_project(project)

    script = Script(project_id=project.id, title="s")

    store.add_script(script)

    shot = make_shot(order=0, text="旁白", duration_ms=6000)

    sub_a, sub_b = shot.sub_shots[0], shot.model_copy().sub_shots[0]

    from core.models.entities import ShotSubShot, new_id



    sub_b = ShotSubShot(

        id=new_id("ssb"),

        start_ms=3000,

        end_ms=6000,

        description="第二子镜",

        camera_motion="static",

    )

    shot = shot.model_copy(update={"sub_shots": [sub_a, sub_b]})

    ctx = AgentRunContext(

        task_brief="",

        work_context={"project_id": project.id, "script_id": script.id},

        script_id=script.id,

        step_id="",

        agent_name="storyboard_agent",

    )

    created, updated, _ = _create_frame_assets_from_data(

        store,

        ctx,

        [{"shot_id": shot.id, "sub_shot_id": sub_a.id, "image_prompt": "子镜A"}],

        [shot],

    )

    assert len(created) == 1

    with pytest.raises(ValueError, match="子镜缺少剧本画面 frame"):

        _assert_sub_shots_have_frames(VideoStyleMode.STORYBOOK, updated)





def test_parse_shots_normalizes_camera_motion_alias():

    """parse_shots_from_data 应将运镜别名解析为 canonical preset。"""

    store = MemoryStore()

    shots = parse_shots_from_data(

        store,

        [shot_design_payload(text="测试旁白", camera_motion="slow_zoom_in")],

    )

    assert len(shots) == 1

    assert shots[0].sub_shots[0].camera_motion == "ken_burns_in"





def test_parse_shots_accepts_legacy_visuals_alias():

    """只读兼容：visuals 映射为 sub_shots。"""

    store = MemoryStore()

    payload = shot_design_payload(text="旁白")

    payload.pop("sub_shots")

    payload["visuals"] = [

        {

            "start_ms": 0,

            "end_ms": 5000,

            "description": "旁白",

            "camera_motion": "static",

        }

    ]

    shots = parse_shots_from_data(store, [payload])

    assert len(shots) == 1

    assert shots[0].sub_shots[0].description == "旁白"

