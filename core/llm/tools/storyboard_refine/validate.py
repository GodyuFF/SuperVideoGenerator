"""分镜复核 tool 入参领域校验（preflight）。"""

from __future__ import annotations

from typing import Any

from core.models.entities import VideoPlan

_VALID_OPS = frozenset({"adjust", "split", "merge", "add", "delete", "regen"})
_REVIEW_SHOT_OPS = frozenset({"adjust", "split", "regen", "delete"})


def _shot_ids_in_plan(plan: VideoPlan) -> set[str]:
    """返回计划稿内全部 shot_id。"""
    return {s.id for s in plan.shots}


def validate_restructure_ops(plan: VideoPlan, ops: list[Any]) -> list[str]:
    """校验 restructure_ops；返回错误信息列表，空表示通过。"""
    errors: list[str] = []
    known = _shot_ids_in_plan(plan)
    if not isinstance(ops, list):
        return ["restructure_ops 须为数组"]

    for i, raw in enumerate(ops):
        if not isinstance(raw, dict):
            errors.append(f"restructure_ops[{i}] 须为对象")
            continue
        kind = str(raw.get("op") or raw.get("kind") or "").strip().lower()
        if kind not in _VALID_OPS:
            errors.append(f"restructure_ops[{i}] 无效 op：{kind or '(空)'}")
            continue

        shot_id = str(raw.get("shot_id") or raw.get("id") or "").strip()
        if kind in ("adjust", "split", "delete", "regen"):
            if not shot_id:
                errors.append(f"restructure_ops[{i}] op={kind} 缺少 shot_id")
            elif shot_id not in known:
                errors.append(f"restructure_ops[{i}] 未知 shot_id：{shot_id}")
        if kind == "split":
            new_shots = raw.get("new_shots")
            if not isinstance(new_shots, list) or len(new_shots) < 2:
                errors.append(f"restructure_ops[{i}] split 须含 new_shots 至少 2 项")
        if kind == "merge":
            ids = [str(x) for x in (raw.get("shot_ids") or []) if x]
            if len(ids) < 2:
                errors.append(f"restructure_ops[{i}] merge 须含 shot_ids 至少 2 项")
            else:
                for sid in ids:
                    if sid not in known:
                        errors.append(f"restructure_ops[{i}] merge 未知 shot_id：{sid}")
        if kind == "add" and not isinstance(raw.get("new_shot"), dict):
            errors.append(f"restructure_ops[{i}] add 须含 new_shot 对象")

    return errors


def validate_review_shot_input(
    plan: VideoPlan | None,
    *,
    shot_id: str,
    patch: Any,
    restructure_op: Any,
) -> list[str]:
    """校验 review_shot 单镜复核入参。"""
    if plan is None or not plan.shots:
        return ["未找到视频计划稿"]
    sid = str(shot_id or "").strip()
    if not sid:
        return ["review_shot 缺少 shot_id"]
    known = _shot_ids_in_plan(plan)
    if sid not in known:
        return [f"未知 shot_id：{sid}"]

    errors: list[str] = []
    has_patch = isinstance(patch, dict) and bool(patch)
    has_op = isinstance(restructure_op, dict) and bool(restructure_op)
    if not has_patch and not has_op:
        errors.append("patch 与 restructure_op 至少一项非空")

    if has_op:
        kind = str(restructure_op.get("op") or restructure_op.get("kind") or "").strip().lower()
        if kind not in _REVIEW_SHOT_OPS:
            errors.append(
                f"review_shot 不支持 op={kind or '(空)'}；跨镜操作请用 review_and_restructure"
            )
        op_sid = str(restructure_op.get("shot_id") or restructure_op.get("id") or "").strip()
        if op_sid and op_sid != sid:
            errors.append(f"restructure_op.shot_id 须与顶层 shot_id 一致（{sid}）")
        if kind == "split":
            new_shots = restructure_op.get("new_shots")
            if not isinstance(new_shots, list) or len(new_shots) < 2:
                errors.append("split 须含 new_shots 至少 2 项")

    if has_patch:
        patch_sid = str(patch.get("shot_id") or patch.get("id") or "").strip()
        if patch_sid and patch_sid != sid:
            errors.append(f"patch.shot_id 须与顶层 shot_id 一致（{sid}）")

    return errors


def validate_shot_detail_patches(plan: VideoPlan, patches: list[Any]) -> list[str]:
    """校验 patches 中 shot_id 均存在于计划稿。"""
    errors: list[str] = []
    if not isinstance(patches, list):
        return ["patches 须为数组"]
    known = _shot_ids_in_plan(plan)
    for i, raw in enumerate(patches):
        if not isinstance(raw, dict):
            errors.append(f"patches[{i}] 须为对象")
            continue
        shot_id = str(raw.get("shot_id") or raw.get("id") or "").strip()
        if not shot_id:
            errors.append(f"patches[{i}] 缺少 shot_id")
        elif shot_id not in known:
            errors.append(f"patches[{i}] 未知 shot_id：{shot_id}")
    return errors


def validate_refine_mutation_input(
    plan: VideoPlan | None,
    *,
    ops: list[Any],
    patches: list[Any],
    require_mutation: bool = False,
) -> list[str]:
    """合并校验复核变更入参。"""
    if plan is None or not plan.shots:
        return ["未找到视频计划稿"]
    errors: list[str] = []
    if require_mutation and not ops and not patches:
        errors.append("patches 与 restructure_ops 至少一项非空")
    if ops:
        errors.extend(validate_restructure_ops(plan, ops))
    if patches:
        errors.extend(validate_shot_detail_patches(plan, patches))
    return errors
