"""仓库布局约束：防止 core/ 与 core/llm/ 职责重复分裂。"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# 已废弃的顶层目录（内容应全部在 core/llm/ 对应子树）
FORBIDDEN_TOP_LEVEL_DIRS = (
    "core/prompt",
    "core/agents",
    "core/a2ui",
)

# 提示词单源：history_summary 必须在 llm/prompt/rules
REQUIRED_PROMPT_FILES = (
    "core/llm/prompt/rules/history_summary.md",
)


def test_no_duplicate_llm_top_level_packages() -> None:
    for rel in FORBIDDEN_TOP_LEVEL_DIRS:
        path = REPO_ROOT / rel
        assert not path.exists(), (
            f"{rel} 已废弃，请迁入 core/llm/ 对应目录后删除"
        )


def test_prompt_rules_at_llm_prompt_root() -> None:
    for rel in REQUIRED_PROMPT_FILES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"缺少提示词文件: {rel}"
