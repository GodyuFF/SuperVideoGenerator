"""Generate re-export shims for moved core.llm packages."""
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
            f"globals().update(_impl.__dict__)\n"
            f"__name__ = _impl.__name__\n"
            f"__doc__ = _impl.__doc__\n",
            encoding="utf-8",
        )

    init_dest = old_root / "__init__.py"
    init_dest.parent.mkdir(parents=True, exist_ok=True)
    init_dest.write_text(
        f'"""Shim package -> {new_pkg}"""\n'
        f"from {new_pkg} import *  # noqa: F403\n",
        encoding="utf-8",
    )


def make_module_shim(dest: Path, mod: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f'"""Shim -> {mod}"""\n'
        f"import importlib\n"
        f"_impl = importlib.import_module({mod!r})\n"
        f"globals().update(_impl.__dict__)\n",
        encoding="utf-8",
    )


def main() -> None:
    make_shim(ROOT / "core" / "agents", ROOT / "core" / "llm" / "agent", "core.llm.agent")
    make_shim(ROOT / "core" / "a2ui", ROOT / "core" / "llm" / "a2ui", "core.llm.a2ui")
    make_shim(ROOT / "core" / "prompt", ROOT / "core" / "llm" / "prompt", "core.llm.prompt")
    make_module_shim(ROOT / "core" / "models" / "llm_request.py", "core.llm.model.llm_request")
    make_module_shim(ROOT / "core" / "models" / "chat_message.py", "core.llm.model.chat_message")
    make_module_shim(ROOT / "core" / "agents" / "react_guard.py", "core.llm.hook.react_guard")
    make_module_shim(ROOT / "core" / "llm" / "master" / "confirm_gates.py", "core.llm.hook.confirm_gates")
    print("shims ok")


if __name__ == "__main__":
    main()
