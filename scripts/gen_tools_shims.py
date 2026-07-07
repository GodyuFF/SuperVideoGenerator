"""Generate re-export shims for core.llm.tools package."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_shim(old_root: Path, new_root: Path, new_pkg: str) -> None:
    for py in new_root.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        rel = py.relative_to(new_root)
        dest = old_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        mod = ".".join([new_pkg, *rel.with_suffix("").parts])
        dest.write_text(
            f'"""Shim -> {mod}"""\n'
            f"import importlib\n"
            f"_impl = importlib.import_module({mod!r})\n"
            f"globals().update(_impl.__dict__)\n",
            encoding="utf-8",
        )
    init_dest = old_root / "__init__.py"
    init_dest.parent.mkdir(parents=True, exist_ok=True)
    init_dest.write_text(
        f'"""Shim package -> {new_pkg}"""\n'
        f"from {new_pkg} import *  # noqa: F403\n",
        encoding="utf-8",
    )


def main() -> None:
    make_shim(ROOT / "core" / "tools", ROOT / "core" / "llm" / "tools", "core.llm.tools")
    agent_tools = ROOT / "core" / "agents" / "tools"
    agent_tools.mkdir(parents=True, exist_ok=True)
    for name, mod in [
        ("specs.py", "core.llm.tools.shared.agent_tools"),
        ("executor.py", "core.llm.tools.shared.executor"),
        ("ask_user.py", "core.llm.tools.shared.ask_user"),
        ("text_asset_list.py", "core.llm.tools.script.list"),
    ]:
        dest = agent_tools / name
        dest.write_text(
            f'"""Shim -> {mod}"""\n'
            f"import importlib\n"
            f"_impl = importlib.import_module({mod!r})\n"
            f"globals().update(_impl.__dict__)\n",
            encoding="utf-8",
        )
    (agent_tools / "__init__.py").write_text(
        '"""Shim -> core.llm.tools.shared"""\n',
        encoding="utf-8",
    )
    web_root = ROOT / "core" / "web_search"
    web_new = ROOT / "core" / "llm" / "tools" / "web_search"
    make_shim(web_root, web_new, "core.llm.tools.web_search")
    print("tools shims ok")


if __name__ == "__main__":
    main()
