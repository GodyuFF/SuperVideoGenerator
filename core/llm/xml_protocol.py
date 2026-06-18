"""ReAct 与 LLM 的 XML 交互协议：构建上下文与解析响应。"""

import re
import xml.etree.ElementTree as ET
from typing import Any

from core.agents.react_core import ReActDecision
from core.llm.react_models import ReActAgentInfo, ReActToolInfo

REACT_SYSTEM_PROMPT = """你是视频生产流水线中的智能 Agent，使用 ReAct（推理 + 行动）模式工作。

你必须且只能使用以下 XML 格式回复，不要输出 Markdown 代码块或其它包裹格式：

<react>
  <thought>你的推理过程（中文）</thought>
  <action>行动名称</action>
  <action_input>
    <备注>可选的补充说明</备注>
  </action_input>
</react>

规则：
1. action 必须从「可用行动」列表中选择；全部完成后 action 必须为 finish。
2. delegate_* 行动表示委派子 Agent（异步执行并等待结果）；tool_* 表示调用工具查询状态。
3. action_input 可为空：使用 <action_input/>。
4. 不要编造未列出的 action。
5. thought 应简洁说明为何选择该 action（委派子 Agent 或调用工具）。"""


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_context_xml(
    role_description: str,
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    """构建发给 LLM 的用户侧 XML 上下文。"""
    actions_xml = "\n".join(f"    <action>{a}</action>" for a in available_actions)
    completed_xml = "\n".join(f"    <item>{c}</item>" for c in completed) or "    <item>无</item>"
    obs_xml = "\n".join(
        f"    <item>{_escape_xml(o)}</item>" for o in observations
    ) or "    <item>无</item>"
    extra_xml = ""
    if extra:
        parts = [f"    <{k}>{_escape_xml(str(v))}</{k}>" for k, v in extra.items()]
        extra_xml = f"\n  <extra>\n" + "\n".join(parts) + "\n  </extra>"

    return f"""<react_context>
  <role>{_escape_xml(role_description)}</role>
  <task_brief>{_escape_xml(task_brief)}</task_brief>
  <available_actions>
{actions_xml}
  </available_actions>
  <completed_actions>
{completed_xml}
  </completed_actions>
  <observations>
{obs_xml}
  </observations>{extra_xml}
</react_context>"""


def build_pure_react_xml(
    conversation_id: str,
    agent_name: str,
    agent: ReActAgentInfo,
    tools: list[ReActToolInfo],
    task_brief: str,
    available_actions: list[str],
    completed: list[str],
    observations: list[str],
    extra: dict[str, Any] | None = None,
    user_summary: str = "",
) -> str:
    """纯净 ReAct 上下文 XML（agent_name、对话 id、agent、tools）。"""
    tools_xml = "\n".join(
        f"    <tool>"
        f"<action>{_escape_xml(t.action_name)}</action>"
        f"<name>{_escape_xml(t.name)}</name>"
        f"<description>{_escape_xml(t.description)}</description>"
        f"</tool>"
        for t in tools
    ) or "    <tool>无</tool>"
    actions_xml = "\n".join(
        f"    <action>{_escape_xml(a)}</action>" for a in available_actions
    )
    completed_xml = "\n".join(
        f"    <item>{_escape_xml(c)}</item>" for c in completed
    ) or "    <item>无</item>"
    obs_xml = "\n".join(
        f"    <item>{_escape_xml(o)}</item>" for o in observations
    ) or "    <item>无</item>"
    extra_xml = ""
    if extra:
        parts = [
            f"    <{k}>{_escape_xml(str(v))}</{k}>" for k, v in extra.items()
        ]
        extra_xml = f"\n  <extra>\n" + "\n".join(parts) + "\n  </extra>"
    if user_summary:
        extra_xml += f"\n  <user_summary>{_escape_xml(user_summary)}</user_summary>"

    return f"""<react_session>
  <conversation_id>{_escape_xml(conversation_id)}</conversation_id>
  <agent_name>{_escape_xml(agent_name)}</agent_name>
  <agent>
    <name>{_escape_xml(agent.name)}</name>
    <display_name>{_escape_xml(agent.display_name)}</display_name>
    <description>{_escape_xml(agent.description)}</description>
  </agent>
  <task_brief>{_escape_xml(task_brief)}</task_brief>
  <tools>
{tools_xml}
  </tools>
  <available_actions>
{actions_xml}
  </available_actions>
  <completed>
{completed_xml}
  </completed>
  <observations>
{obs_xml}
  </observations>{extra_xml}
</react_session>"""


def build_react_session_xml(session: Any) -> str:
    """根据 ReActSession（agent_name、对话 id、agent、tools、sub_agents）构建 LLM 上下文。"""
    agents_xml = "\n".join(
        f"    <sub_agent>"
        f"<delegate_action>{_escape_xml(sa.delegate_action)}</delegate_action>"
        f"<agent_name>{_escape_xml(sa.agent_name)}</agent_name>"
        f"<display_name>{_escape_xml(sa.display_name)}</display_name>"
        f"<description>{_escape_xml(sa.description)}</description>"
        f"</sub_agent>"
        for sa in session.sub_agents
    )
    tools_xml = "\n".join(
        f"    <tool>"
        f"<action>{_escape_xml(t.action_name)}</action>"
        f"<name>{_escape_xml(t.name)}</name>"
        f"<description>{_escape_xml(t.description)}</description>"
        f"</tool>"
        for t in session.tools
    )
    actions_xml = "\n".join(
        f"    <action>{_escape_xml(a)}</action>" for a in session.available_actions()
    )
    completed_xml = "\n".join(
        f"    <item>{_escape_xml(c)}</item>" for c in session.completed_labels()
    ) or "    <item>无</item>"
    obs_xml = "\n".join(
        f"    <item>{_escape_xml(o)}</item>" for o in session.observations
    ) or "    <item>无</item>"
    extra_xml = ""
    if session.extra:
        parts = [
            f"    <{k}>{_escape_xml(str(v))}</{k}>" for k, v in session.extra.items()
        ]
        extra_xml = f"\n  <extra>\n" + "\n".join(parts) + "\n  </extra>"
    if session.user_summary:
        extra_xml += f"\n  <user_summary>{_escape_xml(session.user_summary)}</user_summary>"

    return f"""<react_session>
  <conversation_id>{_escape_xml(session.conversation_id)}</conversation_id>
  <agent_name>{_escape_xml(session.agent_name)}</agent_name>
  <agent>
    <name>{_escape_xml(session.agent.name)}</name>
    <display_name>{_escape_xml(session.agent.display_name)}</display_name>
    <description>{_escape_xml(session.agent.description)}</description>
  </agent>
  <task_brief>{_escape_xml(session.task_brief)}</task_brief>
  <sub_agents>
{agents_xml}
  </sub_agents>
  <tools>
{tools_xml}
  </tools>
  <available_actions>
{actions_xml}
  </available_actions>
  <completed>
{completed_xml}
  </completed>
  <observations>
{obs_xml}
  </observations>{extra_xml}
</react_session>"""


def extract_xml_block(text: str) -> str:
    """从 LLM 回复中提取 <react> 块。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:xml)?\s*(<react[\s\S]*?</react>)\s*```", cleaned, re.I)
    if fence:
        return fence.group(1)
    start = cleaned.find("<react>")
    end = cleaned.rfind("</react>")
    if start != -1 and end != -1:
        return cleaned[start : end + len("</react>")]
    return cleaned


def parse_action_input(element: ET.Element | None) -> dict[str, Any]:
    if element is None:
        return {}
    result: dict[str, Any] = {}
    for child in element:
        tag = child.tag.strip()
        if tag:
            result[tag] = (child.text or "").strip()
    if not result and element.text and element.text.strip():
        result["text"] = element.text.strip()
    return result


def parse_react_xml(text: str) -> ReActDecision:
    """解析 LLM 返回的 ReAct XML。"""
    xml_text = extract_xml_block(text)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        # 宽松回退：正则提取
        thought_m = re.search(r"<thought>([\s\S]*?)</thought>", xml_text, re.I)
        action_m = re.search(r"<action>([\s\S]*?)</action>", xml_text, re.I)
        if not action_m:
            raise ValueError("LLM 响应缺少 <action>")
        return ReActDecision(
            thought=(thought_m.group(1).strip() if thought_m else ""),
            action=action_m.group(1).strip(),
        )

    if root.tag.lower() != "react":
        # 可能包了一层
        react_el = root.find("react")
        if react_el is not None:
            root = react_el

    thought_el = root.find("thought")
    action_el = root.find("action")
    input_el = root.find("action_input")

    if action_el is None or not (action_el.text or "").strip():
        raise ValueError("LLM 响应缺少有效 <action>")

    return ReActDecision(
        thought=(thought_el.text or "").strip() if thought_el is not None else "",
        action=action_el.text.strip(),
        action_input=parse_action_input(input_el),
    )


def format_react_xml(thought: str, action: str) -> str:
    """构造 ReAct XML 响应（测试与脚本化客户端使用）。"""
    return (
        f"<react><thought>{_escape_xml(thought)}</thought>"
        f"<action>{_escape_xml(action)}</action><action_input/></react>"
    )
