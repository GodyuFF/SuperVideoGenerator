"""从 core/llm/prompt/skills 目录加载 Skill 定义（L1/L2 + L3 索引；正文按需读）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.extensions.protocol import SkillToolManifest
from core.llm.prompt.loader import prompt_root
from core.llm.prompt.skills.models import (
    SkillBundle,
    SkillMeta,
    SkillRefIndexEntry,
)

_SKILLS_PKG = prompt_root() / "skills"
_SKILLS_ROOT = _SKILLS_PKG / "builtin"
REF_BODY_MAX_CHARS = 8000


def skills_root() -> Path:
    """返回内置 Skill 内容根目录（与 .py 模块分离，避免 __pycache__ 混入包目录）。"""
    return _SKILLS_ROOT


def skills_package_root() -> Path:
    """返回 skills Python 包目录（含 loader 等模块）。"""
    return _SKILLS_PKG


def _read_json(path: Path) -> dict[str, Any]:
    """读取 JSON 对象文件；缺失或非对象时返回空 dict。"""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _read_text(path: Path) -> str:
    """读取文本文件并 strip；缺失返回空串。"""
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_agent_overlays(skill_dir: Path) -> dict[str, str]:
    """加载 agents/*.md 为 L2 overlay 映射。"""
    agents_dir = skill_dir / "agents"
    if not agents_dir.is_dir():
        return {}
    overlays: dict[str, str] = {}
    for path in agents_dir.glob("*.md"):
        overlays[path.stem] = path.read_text(encoding="utf-8").strip()
    return overlays


def _summary_from_markdown(text: str, limit: int = 80) -> str:
    """从 markdown 取摘要：跳过标题行后取前 limit 字。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    body_parts: list[str] = []
    for ln in lines:
        if ln.startswith("#"):
            continue
        body_parts.append(ln.lstrip("-* ").strip())
        if sum(len(p) for p in body_parts) >= limit:
            break
    joined = " ".join(body_parts).strip()
    if not joined and lines:
        joined = lines[0].lstrip("# ").strip()
    if len(joined) > limit:
        return joined[:limit] + "…"
    return joined


def _title_from_markdown(text: str, fallback: str) -> str:
    """取 markdown 首个 # 标题，否则用 fallback。"""
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            return s.lstrip("# ").strip() or fallback
    return fallback


def _load_ref_index(skill_dir: Path) -> list[SkillRefIndexEntry]:
    """加载 references 索引：优先 index.json，否则扫描 *.md（不读入正文到 Bundle）。"""
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        return []

    index_path = refs_dir / "index.json"
    if index_path.is_file():
        raw = _read_json(index_path)
        entries: list[SkillRefIndexEntry] = []
        for item in raw.get("refs") or []:
            if not isinstance(item, dict):
                continue
            entry = SkillRefIndexEntry.from_dict(item)
            if not entry.id:
                continue
            if not entry.path:
                entry = SkillRefIndexEntry(
                    id=entry.id,
                    title=entry.title or entry.id,
                    path=f"{entry.id}.md",
                    summary=entry.summary,
                    agents=entry.agents,
                )
            entries.append(entry)
        return entries

    entries = []
    for path in sorted(refs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        ref_id = path.stem
        entries.append(
            SkillRefIndexEntry(
                id=ref_id,
                title=_title_from_markdown(text, ref_id),
                path=path.name,
                summary=_summary_from_markdown(text),
                agents=(),
            )
        )
    return entries


def skill_dir_for(skill_id: str) -> Path | None:
    """返回 Skill 目录：优先用户导入，其次内置；不存在则 None。"""
    skill_id = skill_id.strip().lower()
    if not skill_id or ".." in skill_id or "/" in skill_id or "\\" in skill_id:
        return None
    from core.llm.prompt.skills.user_store import user_skill_dir

    try:
        user_dir = user_skill_dir(skill_id)
    except ValueError:
        user_dir = None
    if user_dir is not None and (user_dir / "skill.json").is_file():
        return user_dir
    path = _SKILLS_ROOT / skill_id
    if path.is_dir() and (path / "skill.json").is_file():
        return path
    return None


def _bundle_from_dir(skill_dir: Path, skill_id: str, *, source: str) -> SkillBundle | None:
    """从目录组装 SkillBundle。"""
    meta_raw = _read_json(skill_dir / "skill.json")
    declared_id = str(meta_raw.get("id", skill_id)).strip().lower()
    if declared_id != skill_id:
        return None
    aliases_raw = meta_raw.get("aliases") or []
    aliases = tuple(str(a).strip().lower() for a in aliases_raw if str(a).strip())
    highlights_raw = meta_raw.get("highlights") or []
    highlights = tuple(str(h).strip() for h in highlights_raw if str(h).strip())
    meta = SkillMeta(
        id=skill_id,
        title=str(meta_raw.get("title", skill_id)),
        description=str(meta_raw.get("description", "")),
        aliases=aliases,
        highlights=highlights,
    )
    settings = _read_json(skill_dir / "settings.json")
    tools_raw = meta_raw.get("tools")
    if tools_raw is None:
        tools_raw = _read_json(skill_dir / "tools.json")
    tool_manifest = SkillToolManifest.from_dict(tools_raw if tools_raw else None)
    return SkillBundle(
        meta=meta,
        system_prompt=_read_text(skill_dir / "system.md"),
        settings=settings,
        agent_overlays=_load_agent_overlays(skill_dir),
        ref_index=_load_ref_index(skill_dir),
        tool_manifest=tool_manifest,
        source=source,
    )


@lru_cache(maxsize=32)
def load_skill(skill_id: str) -> SkillBundle | None:
    """加载内置 Skill：元数据 + L2 + ref 索引（不读 L3 正文）。"""
    skill_id = skill_id.strip().lower()
    skill_dir = _SKILLS_ROOT / skill_id
    if not skill_dir.is_dir():
        return None
    return _bundle_from_dir(skill_dir, skill_id, source="builtin")


@lru_cache(maxsize=32)
def load_user_skill(skill_id: str) -> SkillBundle | None:
    """加载用户导入 Skill（data/skills）。"""
    skill_id = skill_id.strip().lower()
    from core.llm.prompt.skills.user_store import user_skill_dir

    try:
        skill_dir = user_skill_dir(skill_id)
    except ValueError:
        return None
    if not (skill_dir / "skill.json").is_file():
        return None
    return _bundle_from_dir(skill_dir, skill_id, source="user")


def list_skills() -> list[SkillMeta]:
    """列出内置 Skill 元数据。"""
    if not _SKILLS_ROOT.is_dir():
        return []
    result: list[SkillMeta] = []
    seen: set[str] = set()
    for child in sorted(_SKILLS_ROOT.iterdir()):
        # 跳过 __pycache__ / 隐藏目录；仅认含 skill.json 的内容包
        if not child.is_dir() or child.name.startswith((".", "__")):
            continue
        bundle = load_skill(child.name)
        if bundle is None or bundle.meta.id in seen:
            continue
        seen.add(bundle.meta.id)
        result.append(bundle.meta)
    return result


def list_user_skills() -> list[SkillMeta]:
    """列出用户导入 Skill 元数据。"""
    from core.llm.prompt.skills.user_store import list_user_skill_ids

    result: list[SkillMeta] = []
    for sid in list_user_skill_ids():
        bundle = load_user_skill(sid)
        if bundle is not None:
            result.append(bundle.meta)
    return result


def resolve_skill_id(token: str) -> str | None:
    """解析 skill id 或 alias（仅内置目录；完整解析见 skill_registry）。"""
    token = token.strip().lower()
    if not token:
        return None
    direct = load_skill(token)
    if direct is not None:
        return direct.meta.id
    for meta in list_skills():
        if token in meta.aliases:
            return meta.id
    return None


def _resolve_ref_path(skill_id: str, entry: SkillRefIndexEntry) -> Path | None:
    """将索引条目解析为 references 下的安全路径；越界返回 None。"""
    skill_dir = skill_dir_for(skill_id)
    if skill_dir is None:
        return None
    refs_root = (skill_dir / "references").resolve()
    if not refs_root.is_dir():
        return None
    rel = entry.path.replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    target = (refs_root / rel).resolve()
    try:
        target.relative_to(refs_root)
    except ValueError:
        return None
    if not target.is_file():
        return None
    return target


def list_skill_ref_entries(
    skill_id: str,
    *,
    agent_name: str | None = None,
) -> list[SkillRefIndexEntry]:
    """列出 Skill 的 references 索引；可按 Agent 过滤。"""
    from core.extensions.skill_registry import get_skill

    bundle = get_skill(skill_id)
    if bundle is None:
        return []
    if not agent_name:
        return list(bundle.ref_index)
    return [
        e
        for e in bundle.ref_index
        if not e.agents or agent_name in e.agents
    ]


def read_skill_ref_body(
    skill_id: str,
    ref_id: str,
    *,
    max_chars: int = REF_BODY_MAX_CHARS,
) -> dict[str, Any]:
    """
    按需读取 references 正文。

    返回 dict：ok, ref_id, title, content, truncated, content_length, error?
    """
    from core.extensions.skill_registry import get_skill

    skill_id = skill_id.strip().lower()
    ref_id = ref_id.strip()
    bundle = get_skill(skill_id)
    if bundle is None:
        return {
            "ok": False,
            "ref_id": ref_id,
            "error": f"未知 Skill「{skill_id}」",
            "content": "",
            "truncated": False,
            "content_length": 0,
        }
    entry = next((e for e in bundle.ref_index if e.id == ref_id), None)
    if entry is None:
        return {
            "ok": False,
            "ref_id": ref_id,
            "error": f"Skill「{skill_id}」无参考「{ref_id}」",
            "content": "",
            "truncated": False,
            "content_length": 0,
        }
    # 扩展 Skill 可能无本地目录：仅支持内置 filesystem
    path = _resolve_ref_path(skill_id, entry)
    if path is None:
        return {
            "ok": False,
            "ref_id": ref_id,
            "title": entry.title,
            "error": f"无法安全读取参考「{ref_id}」（仅支持内置 Skill 的 references/）",
            "content": "",
            "truncated": False,
            "content_length": 0,
        }
    text = path.read_text(encoding="utf-8")
    length = len(text)
    truncated = False
    if max_chars > 0 and length > max_chars:
        text = text[:max_chars] + f"\n\n…（已截断，原文约 {length} 字，可缩小范围或再次查阅）"
        truncated = True
    return {
        "ok": True,
        "ref_id": entry.id,
        "title": entry.title,
        "path": entry.path,
        "content": text,
        "truncated": truncated,
        "content_length": length,
    }
