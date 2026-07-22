"""用户导入的 Skill 目录（data/skills）读写与导入。"""

from __future__ import annotations

import io
import logging
import re
import shutil
import zipfile
from pathlib import Path

from core.store.project_paths import resolve_data_root

logger = logging.getLogger("core.llm.prompt.skills.user_store")

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


def user_skills_root() -> Path:
    """用户 Skill 根目录 data/skills。"""
    return (resolve_data_root() / "skills").resolve()


def safe_skill_id(skill_id: str) -> str:
    """校验并规范化 skill id。"""
    sid = str(skill_id or "").strip().lower()
    if not _SAFE_ID.match(sid):
        raise ValueError(
            "Skill id 仅允许小写字母、数字、下划线与连字符，且须以字母或数字开头"
        )
    return sid


def user_skill_dir(skill_id: str) -> Path:
    """返回用户 Skill 目录路径。"""
    return user_skills_root() / safe_skill_id(skill_id)


def is_user_skill(skill_id: str) -> bool:
    """是否为用户导入的 Skill（存在于 data/skills）。"""
    try:
        path = user_skill_dir(skill_id)
    except ValueError:
        return False
    return (path / "skill.json").is_file()


def list_user_skill_ids() -> list[str]:
    """列出用户 Skill 目录 id。"""
    root = user_skills_root()
    if not root.is_dir():
        return []
    ids: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "skill.json").is_file():
            ids.append(child.name.lower())
    return ids


def _validate_skill_tree(skill_dir: Path, expected_id: str | None = None) -> str:
    """校验 Skill 目录结构，返回规范化 id；失败抛 ValueError。"""
    from core.llm.prompt.skills.validate import validate_skill_directory

    report = validate_skill_directory(skill_dir)
    if expected_id and report.skill_id and report.skill_id != expected_id:
        raise ValueError(
            f"skill.json id「{report.skill_id}」与目录「{expected_id}」不一致"
        )
    if not report.ok:
        raise ValueError(report.errors[0] if report.errors else "Skill 格式校验失败")
    assert report.skill_id
    return report.skill_id


def _copy_tree(src: Path, dst: Path) -> None:
    """复制 Skill 目录到目标（覆盖已存在目标）。"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def import_skill_from_directory(src_dir: Path, *, overwrite: bool = False) -> str:
    """从已解压目录导入 Skill，返回 skill id。"""
    src_dir = src_dir.resolve()
    if not src_dir.is_dir():
        raise ValueError("导入源不是目录")
    # 支持 src 本身是 skill 根，或仅含一个子目录
    if not (src_dir / "skill.json").is_file():
        children = [c for c in src_dir.iterdir() if c.is_dir()]
        if len(children) == 1 and (children[0] / "skill.json").is_file():
            src_dir = children[0]
        else:
            raise ValueError("未找到 skill.json（可放在 zip 根或单一子目录内）")
    sid = _validate_skill_tree(src_dir)
    dest = user_skill_dir(sid)
    if dest.exists() and not overwrite:
        raise ValueError(f"Skill「{sid}」已存在，请设置 overwrite=true 覆盖")
    # 禁止覆盖内置同名：若仅想装用户包，允许覆盖用户；内置仍优先于用户？ 
    # 策略：用户同 id 覆盖用户目录；get_skill 用户优先于内置，故可覆盖内置行为
    user_skills_root().mkdir(parents=True, exist_ok=True)
    _copy_tree(src_dir, dest)
    _validate_skill_tree(dest, expected_id=sid)
    return sid


def import_skill_from_zip(data: bytes, *, overwrite: bool = False) -> str:
    """从 zip 字节流导入 Skill。"""
    if not data:
        raise ValueError("空的 zip 内容")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("无效的 zip 文件") from exc
    with zf:
        # 拒绝路径穿越
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"zip 含非法路径：{info.filename}")
        import tempfile

        with tempfile.TemporaryDirectory(prefix="svg_skill_") as tmp:
            tmp_path = Path(tmp)
            zf.extractall(tmp_path)
            return import_skill_from_directory(tmp_path, overwrite=overwrite)


def delete_user_skill(skill_id: str) -> None:
    """删除用户导入的 Skill（不可删内置）。"""
    sid = safe_skill_id(skill_id)
    if not is_user_skill(sid):
        raise ValueError(f"「{sid}」不是用户导入的 Skill，无法删除")
    shutil.rmtree(user_skill_dir(sid))
