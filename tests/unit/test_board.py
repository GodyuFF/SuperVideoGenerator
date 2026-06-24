"""看板构建单元测试。"""

import pytest

from core.board.builder import BoardBuilder, BOARD_KINDS
from core.models.entities import (
    AssetScope,
    MediaAsset,
    MediaAssetType,
    Project,
    Script,
    TextAsset,
    TextAssetType,
    VideoPlan,
    VideoPlanShot,
    VideoStyleMode,
)
from core.store.memory import MemoryStore


@pytest.fixture
def sample_store() -> MemoryStore:
    store = MemoryStore()
    project = Project(title="测试项目")
    store.add_project(project)
    script = Script(project_id=project.id, title="第一集", content_md="# 开场\n\n故事开始")
    store.add_script(script)

    char = TextAsset(
        project_id=project.id,
        type=TextAssetType.CHARACTER,
        scope=AssetScope.PROJECT_SHARED,
        name="主角",
        content={"appearance": "年轻程序员"},
        source_script_id=script.id,
    )
    store.add_text_asset(char)

    plot = TextAsset(
        project_id=project.id,
        script_id=script.id,
        type=TextAssetType.PLOT,
        name="开场",
        content={"text": "故事开始"},
    )
    store.add_text_asset(plot)

    vp = VideoPlan(
        script_id=script.id,
        mode=VideoStyleMode.DYNAMIC_IMAGE,
        shots=[
            VideoPlanShot(order=0, narration_text="你好世界", duration_ms=3000),
        ],
    )
    store.set_video_plan(vp)

    store.add_media_asset(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            type=MediaAssetType.IMAGE,
            name="主角图",
            url="https://cdn.example.com/hero.png",
            source_asset_id=char.id,
        )
    )

    return store


@pytest.mark.parametrize("kind", BOARD_KINDS)
def test_build_all_board_kinds(sample_store: MemoryStore, kind: str):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build(kind, project_id, script_id)
    assert view.kind == kind
    assert view.title


def test_overview_lists_scripts(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("overview", project_id, script_id)
    assert len(view.items) == 1
    assert view.items[0]["title"] == "第一集"


def test_character_board_links_image(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("character", project_id, script_id)
    assert len(view.items) == 1
    assert view.items[0]["images"]


def test_project_graph_has_edges(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("project_graph", project_id, script_id)
    assert len(view.nodes) >= 3
    assert len(view.edges) >= 2


def test_pipeline_order(sample_store: MemoryStore):
    project_id = list(sample_store.projects.keys())[0]
    script_id = list(sample_store.scripts.keys())[0]
    view = BoardBuilder(sample_store).build("pipeline", project_id, script_id)
    assert view.pipeline
    assert view.pipeline[0].step_type == "script_design"
