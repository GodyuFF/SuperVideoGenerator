"""生图失败结构化解析测试。"""

import json

from core.llm.hook.react_guard import ImageGenerationAbortError
from core.llm.tools.image.agnes_client import AgnesImageGenerationError
from core.llm.tools.image.errors import (
    build_failure_item,
    build_image_gen_failure_analysis,
    classify_image_gen_error,
    format_image_gen_abort_message,
    format_image_gen_failure_observation,
    parse_agnes_api_error_body,
)


def test_parse_agnes_content_policy_error():
    body = json.dumps(
        {
            "error": {
                "message": "Unable to generate this content. Please modify your prompt and try again.",
                "type": "invalid_request_error",
                "param": "prompt",
                "code": "content_policy_violation",
            }
        }
    )
    parsed = parse_agnes_api_error_body(400, body)
    assert parsed["error_code"] == "content_policy_violation"
    assert "Unable to generate" in parsed["message"]


def test_classify_content_policy():
    category = classify_image_gen_error(
        message="Unable to generate this content.",
        error_code="content_policy_violation",
        error_type="invalid_request_error",
        param="prompt",
        http_status=400,
    )
    assert category == "content_policy"


def test_format_abort_message_lists_all_failures():
    failures = [
        build_failure_item(
            source_text_asset_id="txt_a",
            asset_name="场景A",
            image_prompt="tiger in forest",
            error_message="policy block",
            error_code="content_policy_violation",
        ),
        build_failure_item(
            source_text_asset_id="txt_b",
            asset_name="场景B",
            image_prompt="lion hunting",
            error_message="policy block 2",
            error_code="content_policy_violation",
        ),
    ]
    analysis = build_image_gen_failure_analysis(
        failures, succeeded_count=1, total_count=3
    )
    message = format_image_gen_abort_message(analysis)
    assert "2/3" in message
    assert "txt_a" in message
    assert "txt_b" in message
    assert "场景A" in message
    assert "场景B" in message


def test_image_generation_abort_error_carries_analysis():
    item = build_failure_item(
        source_text_asset_id="txt_x",
        asset_name="测试",
        image_prompt="prompt",
        error_message="blocked",
        error_code="content_policy_violation",
    )
    analysis = build_image_gen_failure_analysis([item], total_count=1)
    exc = ImageGenerationAbortError(
        "generate_images",
        format_image_gen_abort_message(analysis),
        failure_analysis=analysis,
    )
    assert exc.needs_upstream_prompt_adjustment() is True


def test_format_observation_includes_recovery_guidance():
    item = build_failure_item(
        source_text_asset_id="txt_x",
        asset_name="清晨密林",
        image_prompt="tiger walking",
        error_message="Unable to generate this content.",
        error_code="content_policy_violation",
    )
    analysis = build_image_gen_failure_analysis([item], total_count=1)
    obs = format_image_gen_failure_observation(analysis)
    assert "【失败明细（全部）】" in obs
    assert "delegate_script_design" in obs
    assert "txt_x" in obs
    assert "内容策略" in obs


def test_agnes_error_structured_fields():
    err = AgnesImageGenerationError(
        "Agnes API 错误 400: blocked",
        http_status=400,
        error_code="content_policy_violation",
        error_type="invalid_request_error",
        param="prompt",
        api_message="blocked",
    )
    assert err.error_code == "content_policy_violation"
    assert err.http_status == 400
