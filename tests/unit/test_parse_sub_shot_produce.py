"""子镜 produce_mode / 画面时段解析与结构校验集成测试。"""



from core.edit.shot_validate import validate_shot_structure

from core.llm.agent.llm_action import _parse_sub_shots

from core.models.entities import Shot, ShotSubShot, ShotSubShotImage





def test_parse_sub_shots_keeps_produce_mode_and_image_timing():

    subs = _parse_sub_shots([

        {

            "start_ms": 0,

            "end_ms": 4000,

            "description": "冲刺",

            "produce_mode": "img2video",

            "produce_rationale": "动作强",

            "images": [

                {"kind": "static", "frame_asset_id": "txt_f1", "start_ms": 500, "end_ms": 2000},

            ],

        }

    ])

    assert len(subs) == 1

    assert subs[0].produce_mode == "img2video"

    assert subs[0].produce_rationale == "动作强"

    assert subs[0].images[0].start_ms == 500

    assert subs[0].images[0].end_ms == 2000





def test_parse_sub_shots_coerces_legacy_ai_video():

    subs = _parse_sub_shots([

        {

            "start_ms": 0,

            "end_ms": 4000,

            "description": "冲刺",

            "produce_mode": "ai_video",

        }

    ])

    assert subs[0].produce_mode == "img2video"





def test_parse_sub_shots_infers_mode_and_fills_timing_when_absent():

    subs = _parse_sub_shots([

        {

            "start_ms": 0,

            "end_ms": 3000,

            "description": "空镜",

            "images": [{"kind": "static", "frame_asset_id": "txt_f1"}],

        }

    ])

    assert subs[0].produce_mode == "still"

    assert subs[0].images[0].start_ms == 0

    assert subs[0].images[0].end_ms == 3000





def test_validate_shot_structure_flags_bad_image_timing() -> None:

    """画面 end_ms 超出子镜区间时结构校验应报告问题。"""

    shot = Shot(

        id="bad_img_timing",

        order=0,

        duration_ms=3000,

        sub_shots=[

            ShotSubShot(

                id="ss1",

                start_ms=0,

                end_ms=3000,

                description="画面",

                images=[ShotSubShotImage(start_ms=0, end_ms=4000)],

            )

        ],

    )

    issues = validate_shot_structure(shot)

    assert any("images[0]" in i or "区间" in i for i in issues)


