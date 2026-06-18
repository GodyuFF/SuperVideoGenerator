"""单元测试：XML ReAct 协议解析。"""

from core.llm.xml_protocol import build_context_xml, parse_react_xml


def test_parse_react_xml_basic():
    raw = """
<react>
  <thought>应先创建剧情资产</thought>
  <action>create_plot</action>
  <action_input/>
</react>
"""
    d = parse_react_xml(raw)
    assert d.thought == "应先创建剧情资产"
    assert d.action == "create_plot"
    assert d.action_input == {}


def test_parse_react_xml_with_fence():
    raw = """```xml
<react>
  <thought>完成</thought>
  <action>finish</action>
  <action_input><备注>done</备注></action_input>
</react>
```"""
    d = parse_react_xml(raw)
    assert d.action == "finish"
    assert d.action_input.get("备注") == "done"


def test_build_context_xml_contains_actions():
    xml = build_context_xml(
        role_description="测试 Agent",
        task_brief="生成剧本",
        available_actions=["parse_brief", "finish"],
        completed=["parse_brief"],
        observations=["已解析"],
    )
    assert "<action>parse_brief</action>" in xml
    assert "<action>finish</action>" in xml
    assert "生成剧本" in xml
