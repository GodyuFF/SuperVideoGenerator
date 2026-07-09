"""将 opencut-classic 编辑器源码复制到 apps/web/src/editor/opencut。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "opencut-classic" / "apps" / "web" / "src"
DST = ROOT / "apps" / "web" / "src" / "editor" / "opencut"

SKIP_TOP_LEVEL = {
    "app",
    "auth",
    "blog",
    "db",
    "env",
    "site",
    "feedback",
}

SKIP_PARTS = {"/__tests__/", "\\__tests__\\"}

PRESERVE_FILES = {
    "ClassicEditorLayout.tsx",
    "SvfClassicEditor.tsx",
    "svf-storage-bridge.ts",
}


def should_skip(path: Path) -> bool:
    s = str(path)
    return any(p in s for p in SKIP_PARTS)


def transform_content(text: str) -> str:
    text = re.sub(r'^"use client";\s*\n', "", text, flags=re.MULTILINE)
    text = text.replace('from "@/', 'from "@opencut/')
    text = text.replace('import "@/', 'import "@opencut/')
    return text


def backup_preserve() -> dict[str, str]:
    backed: dict[str, str] = {}
    if not DST.is_dir():
        return backed
    for name in PRESERVE_FILES:
        p = DST / name
        if p.is_file():
            backed[name] = p.read_text(encoding="utf-8")
    shims = DST / "shims"
    if shims.is_dir():
        for p in shims.rglob("*"):
            if p.is_file():
                backed[f"shims/{p.relative_to(shims).as_posix()}"] = p.read_text(encoding="utf-8")
    return backed


def restore_preserve(backed: dict[str, str]) -> None:
    for rel, content in backed.items():
        out = DST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")


def main() -> None:
    backed = backup_preserve()
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)

    copied = 0
    for src_dir in sorted(SRC.iterdir()):
        if not src_dir.is_dir():
            continue
        if src_dir.name in SKIP_TOP_LEVEL:
            continue
        for path in src_dir.rglob("*"):
            if not path.is_file():
                continue
            if should_skip(path):
                continue
            rel = path.relative_to(SRC)
            out = DST / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix in {".ts", ".tsx", ".css"}:
                out.write_text(transform_content(path.read_text(encoding="utf-8")), encoding="utf-8")
            else:
                shutil.copy2(path, out)
            copied += 1

    globals_css = SRC / "app" / "globals.css"
    if globals_css.is_file():
        (DST / "globals.css").write_text(globals_css.read_text(encoding="utf-8"), encoding="utf-8")
        copied += 1

    restore_preserve(backed)
    print(f"ported {copied} files to {DST}")


if __name__ == "__main__":
    main()
