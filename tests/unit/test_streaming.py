"""ReactJsonThoughtParser 流式解析单元测试。"""

from core.llm.streaming import ReactJsonThoughtParser


def test_json_thought_parser_full_chunk():
    parser = ReactJsonThoughtParser()
    delta = parser.feed('{"thought":"老虎吃肉","action":"finish"}')
    assert delta == "老虎吃肉"
    assert parser.feed("") == ""


def test_json_thought_parser_streaming_chunks():
    parser = ReactJsonThoughtParser()
    parts = []
    for chunk in ['{"thought":"老', '虎吃', '肉","action":"finish"}']:
        parts.append(parser.feed(chunk))
    assert "".join(parts) == "老虎吃肉"


def test_json_thought_parser_partial_escape():
    parser = ReactJsonThoughtParser()
    raw = '{"thought":"用户\\n需求","action":"finish"}'
    emitted = ""
    for i in range(0, len(raw), 4):
        emitted += parser.feed(raw[i : i + 4])
    assert emitted == "用户\n需求"
