"""ReactXmlThoughtParser 流式解析单元测试。"""

from core.llm.streaming import ReactXmlThoughtParser


def test_thought_parser_full_chunk():
    parser = ReactXmlThoughtParser()
    delta = parser.feed("<thought>老虎吃肉</thought>")
    assert delta == "老虎吃肉"
    assert parser.feed("") == ""


def test_thought_parser_streaming_chunks():
    parser = ReactXmlThoughtParser()
    parts = []
    for chunk in ["<thought>老", "虎吃", "肉</thought>"]:
        parts.append(parser.feed(chunk))
    assert "".join(parts) == "老虎吃肉"
    assert "</thought" not in "".join(parts)


def test_thought_parser_partial_close_tag_not_emitted():
    parser = ReactXmlThoughtParser()
    parts = []
    for chunk in ["<thought>用", "户需", "求</thought", ">"]:
        parts.append(parser.feed(chunk))
    combined = "".join(parts)
    assert combined == "用户需求"
    assert "</thought" not in combined
    assert "<" not in combined


def test_thought_parser_with_react_wrapper():
    parser = ReactXmlThoughtParser()
    text = "<react>\n  <thought>分析主题</thought>\n  <action>finish</action>\n</react>"
    emitted = ""
    for i in range(0, len(text), 5):
        emitted += parser.feed(text[i : i + 5])
    assert emitted == "分析主题"
    assert "<" not in emitted and "thought" not in emitted
