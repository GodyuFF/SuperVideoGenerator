"""Skill 包格式校验：目录 / zip → 结构化检查报告。"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.llm.prompt.skills.user_store import (
    _SAFE_ID,
    is_user_skill,
    safe_skill_id,
    user_skill_dir,
)


@dataclass
class SkillCheckItem:
    """单项格式检查结果。"""

    id: str
    label: str
    ok: bool
    required: bool = True
    detail: str = ""


@dataclass
class SkillValidationReport:
    """Skill 格式校验报告（供 API / 导入闸展示）。"""

    ok: bool
    skill_id: str | None = None
    title: str | None = None
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    already_exists: bool = False
    checks: list[SkillCheckItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API JSON。"""
        return {
            "ok": self.ok,
            "skill_id": self.skill_id,
            "title": self.title,
            "description": self.description,
            "aliases": list(self.aliases),
            "already_exists": self.already_exists,
            "checks": [asdict(c) for c in self.checks],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _resolve_skill_root(src_dir: Path) -> Path | None:
    """定位含 skill.json 的 Skill 根目录。"""
    if (src_dir / "skill.json").is_file():
        return src_dir
    children = [c for c in src_dir.iterdir() if c.is_dir()]
    if len(children) == 1 and (children[0] / "skill.json").is_file():
        return children[0]
    return None


def validate_skill_directory(src_dir: Path) -> SkillValidationReport:
    """校验已解压 Skill 目录格式。"""
    report = SkillValidationReport(ok=False)
    src_dir = src_dir.resolve()
    if not src_dir.is_dir():
        report.errors.append("导入源不是目录")
        report.checks.append(
            SkillCheckItem("root_dir", "Skill 根目录", False, detail="不是目录")
        )
        return report

    root = _resolve_skill_root(src_dir)
    has_json = root is not None
    report.checks.append(
        SkillCheckItem(
            "skill_json",
            "含 skill.json（zip 根或单一子目录）",
            has_json,
            detail="" if has_json else "未找到 skill.json",
        )
    )
    if root is None:
        report.errors.append("未找到 skill.json（可放在 zip 根或单一子目录内）")
        return report

    meta_path = root / "skill.json"
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.checks.append(
            SkillCheckItem("skill_json_parse", "skill.json 可解析", False, detail=str(exc))
        )
        report.errors.append(f"skill.json 不是合法 JSON：{exc}")
        return report
    if not isinstance(raw, dict):
        report.checks.append(
            SkillCheckItem("skill_json_object", "skill.json 为对象", False)
        )
        report.errors.append("skill.json 必须是 JSON 对象")
        return report
    report.checks.append(SkillCheckItem("skill_json_parse", "skill.json 可解析", True))

    declared = str(raw.get("id") or root.name).strip().lower()
    id_ok = bool(_SAFE_ID.match(declared))
    report.checks.append(
        SkillCheckItem(
            "skill_id",
            "id 合法（小写字母数字_-/，≤64）",
            id_ok,
            detail=declared or "（空）",
        )
    )
    if not id_ok:
        report.errors.append(
            "Skill id 仅允许小写字母、数字、下划线与连字符，且须以字母或数字开头"
        )
        return report

    try:
        sid = safe_skill_id(declared)
    except ValueError as exc:
        report.errors.append(str(exc))
        return report

    report.skill_id = sid
    dir_ok = root.name.lower() == sid
    report.checks.append(
        SkillCheckItem(
            "dir_name",
            "目录名与 id 一致",
            dir_ok,
            detail=f"目录={root.name} / id={sid}",
        )
    )
    if not dir_ok:
        report.errors.append(f"目录名须与 skill id 一致（期望 {sid}）")

    title = str(raw.get("title") or "").strip()
    title_ok = bool(title)
    report.title = title or None
    report.checks.append(
        SkillCheckItem("title", "skill.json 含 title", title_ok, detail=title or "缺失")
    )
    if not title_ok:
        report.errors.append("skill.json 缺少 title")

    desc = str(raw.get("description") or "").strip()
    report.description = desc
    report.checks.append(
        SkillCheckItem(
            "description",
            "建议填写 description",
            bool(desc),
            required=False,
            detail=desc[:80] if desc else "未填写（可选）",
        )
    )
    if not desc:
        report.warnings.append("未填写 description，对话列表将缺少简介")

    aliases_raw = raw.get("aliases") or []
    if isinstance(aliases_raw, list):
        report.aliases = [str(a).strip().lower() for a in aliases_raw if str(a).strip()]
    else:
        report.checks.append(
            SkillCheckItem("aliases", "aliases 为数组", False, required=False)
        )
        report.warnings.append("aliases 应为字符串数组，已忽略")

    system_path = root / "system.md"
    system_ok = system_path.is_file() and bool(system_path.read_text(encoding="utf-8").strip())
    report.checks.append(
        SkillCheckItem(
            "system_md",
            "含非空 system.md（L2 说明）",
            system_ok,
            detail="已找到" if system_ok else "缺失或为空",
        )
    )
    if not system_ok:
        report.errors.append("缺少非空 system.md")

    refs = root / "references"
    has_refs = refs.is_dir() and any(refs.glob("*.md"))
    report.checks.append(
        SkillCheckItem(
            "references",
            "可选 references/*.md",
            has_refs,
            required=False,
            detail="有参考文件" if has_refs else "无（可选）",
        )
    )

    agents_dir = root / "agents"
    has_agents = agents_dir.is_dir() and any(agents_dir.glob("*.md"))
    report.checks.append(
        SkillCheckItem(
            "agents",
            "可选 agents/<agent>.md",
            has_agents,
            required=False,
            detail="有 Agent 补充" if has_agents else "无（可选）",
        )
    )

    report.already_exists = is_user_skill(sid) or (user_skill_dir(sid) / "skill.json").is_file()
    report.ok = len(report.errors) == 0
    return report


def validate_skill_zip(data: bytes) -> SkillValidationReport:
    """校验 Skill zip 字节流格式（不落盘）。"""
    report = SkillValidationReport(ok=False)
    if not data:
        report.errors.append("空的 zip 内容")
        report.checks.append(SkillCheckItem("zip_bytes", "zip 非空", False))
        return report
    report.checks.append(SkillCheckItem("zip_bytes", "zip 非空", True))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        report.errors.append("无效的 zip 文件")
        report.checks.append(
            SkillCheckItem("zip_parse", "zip 可解压", False, detail=str(exc))
        )
        return report

    with zf:
        report.checks.append(SkillCheckItem("zip_parse", "zip 可解压", True))
        path_ok = True
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                path_ok = False
                report.errors.append(f"zip 含非法路径：{info.filename}")
                break
        report.checks.append(
            SkillCheckItem(
                "zip_paths",
                "无路径穿越",
                path_ok,
                detail="" if path_ok else "含 .. 或绝对路径",
            )
        )
        if not path_ok:
            return report
        with tempfile.TemporaryDirectory(prefix="svg_skill_validate_") as tmp:
            tmp_path = Path(tmp)
            zf.extractall(tmp_path)
            nested = validate_skill_directory(tmp_path)
            # 合并 zip 层 checks 在前
            nested.checks = report.checks + nested.checks
            return nested
