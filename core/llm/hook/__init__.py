"""编排生命周期 Hook 扩展点。"""

from core.llm.hook.confirm_gates import (
    CONFIRM_AFTER_STEP,
    CONFIRM_BEFORE_ACTION,
    GateMeta,
    build_script_structure_summary,
)
from core.llm.hook.react_guard import (
    DuplicateActionAbortError,
    ImageGenerationAbortError,
    ReActLoopGuard,
    action_signature,
)
from core.llm.hook.registry import HookRegistry, ToolCallHook

__all__ = [
    "CONFIRM_AFTER_STEP",
    "CONFIRM_BEFORE_ACTION",
    "DuplicateActionAbortError",
    "ImageGenerationAbortError",
    "GateMeta",
    "HookRegistry",
    "ReActLoopGuard",
    "ToolCallHook",
    "action_signature",
    "build_script_structure_summary",
]
