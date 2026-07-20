"""视频风格与 PromptProfile 一对一同步。"""

from __future__ import annotations

from core.llm.agent.profile_seed import BUILTIN_STYLE_PROFILE_IDS, is_builtin_style_mode
from core.models.agent_config import AgentRegistryData, CustomPromptProfile, CustomStyleMode
from core.models.entities import VideoStyleMode

_BUILTIN_STYLE_ID_SET = frozenset(BUILTIN_STYLE_PROFILE_IDS)

# 已下线的风格/Profile id：加载时从 registry 移除并回退 prompt 映射
_REMOVED_STYLE_IDS = frozenset(
    {
        "dynamic_comic",
        "marketing_video",
        "marketing",
    }
)


def removed_style_ids() -> frozenset[str]:
    """返回已下线、需从 registry/UI 移除的视频风格 id。"""
    return _REMOVED_STYLE_IDS


def _purge_removed_styles(registry: AgentRegistryData) -> tuple[AgentRegistryData, bool]:
    """从 registry 移除已下线风格，并将 prompt_profiles 回退为 storybook。"""
    removed = _REMOVED_STYLE_IDS
    changed = False

    new_styles = [sm for sm in registry.style_modes if sm.id not in removed]
    if len(new_styles) != len(registry.style_modes):
        changed = True

    new_profiles = [cp for cp in registry.custom_profiles if cp.id not in removed]
    if len(new_profiles) != len(registry.custom_profiles):
        changed = True

    new_prompt_profiles = dict(registry.prompt_profiles)
    for agent, profile_id in list(registry.prompt_profiles.items()):
        if profile_id in removed:
            new_prompt_profiles[agent] = VideoStyleMode.STORYBOOK.value
            changed = True

    if not changed:
        return registry, False

    return (
        registry.model_copy(
            update={
                "style_modes": new_styles,
                "custom_profiles": new_profiles,
                "prompt_profiles": new_prompt_profiles,
            }
        ),
        True,
    )


def _is_custom_style(style: CustomStyleMode) -> bool:
    """是否为非内置的自定义视频风格。"""
    if style.builtin or style.id in _BUILTIN_STYLE_ID_SET:
        return False
    return True


def sync_style_profile_pairs(registry: AgentRegistryData) -> tuple[AgentRegistryData, bool]:
    """同步 style_modes 与 custom_profiles，强制 1:1；返回 (registry, changed)。"""
    registry, purged = _purge_removed_styles(registry)
    changed = purged
    custom_styles = [sm for sm in registry.style_modes if _is_custom_style(sm)]
    style_by_id = {sm.id: sm for sm in custom_styles}
    profile_by_id = {cp.id: cp for cp in registry.custom_profiles}

    new_styles: list[CustomStyleMode] = []
    for sm in registry.style_modes:
        if not _is_custom_style(sm):
            new_styles.append(sm)
            continue
        fixed = sm.model_copy()
        if fixed.default_prompt_profile != fixed.id:
            fallback = fixed.default_prompt_profile or VideoStyleMode.STORYBOOK.value
            if fallback not in _BUILTIN_STYLE_ID_SET and fallback not in style_by_id:
                fallback = VideoStyleMode.STORYBOOK.value
            fixed = fixed.model_copy(
                update={
                    "default_prompt_profile": fixed.id,
                    "builtin": False,
                }
            )
            changed = True
        new_styles.append(fixed)
        style_by_id[fixed.id] = fixed

    new_profiles: list[CustomPromptProfile] = []
    for sm in custom_styles:
        sm = style_by_id.get(sm.id, sm)
        existing = profile_by_id.get(sm.id)
        if existing:
            if existing.label != sm.label:
                existing = existing.model_copy(update={"label": sm.label})
                changed = True
            new_profiles.append(existing)
            continue
        based_on = sm.default_prompt_profile
        if based_on == sm.id or based_on not in _BUILTIN_STYLE_ID_SET:
            based_on = VideoStyleMode.STORYBOOK.value
        new_profiles.append(
            CustomPromptProfile(id=sm.id, label=sm.label, based_on=based_on)
        )
        changed = True

    style_ids = {sm.id for sm in custom_styles}
    for cp in list(registry.custom_profiles):
        if cp.id in _BUILTIN_STYLE_ID_SET:
            continue
        if cp.id not in style_ids:
            changed = True
            continue
        if cp not in new_profiles:
            new_profiles.append(cp)

    if new_styles != registry.style_modes:
        changed = True
    if new_profiles != registry.custom_profiles:
        changed = True

    if not changed:
        return registry, False

    return (
        registry.model_copy(
            update={
                "style_modes": new_styles,
                "custom_profiles": new_profiles,
            }
        ),
        True,
    )


def validate_style_profile_patch(
    style_modes: list[CustomStyleMode] | None,
    custom_profiles: list[CustomPromptProfile] | None,
) -> None:
    """PATCH 时校验风格与 Profile 一对一。"""
    if style_modes is None:
        return
    custom_styles = [sm for sm in style_modes if _is_custom_style(sm)]
    profile_ids = {cp.id for cp in (custom_profiles or [])}
    for sm in custom_styles:
        if sm.builtin:
            raise ValueError(f"不可通过 PATCH 提交内置风格：{sm.id}")
        if sm.default_prompt_profile != sm.id:
            raise ValueError(
                f"风格 {sm.id} 的 default_prompt_profile 必须等于自身 id（1:1）"
            )
        if sm.id not in profile_ids:
            raise ValueError(
                f"风格 {sm.id} 缺少同名 custom_profiles 条目"
            )
    for cp in custom_profiles or []:
        if cp.id in _BUILTIN_STYLE_ID_SET:
            continue
        if cp.id not in {sm.id for sm in custom_styles}:
            if not any(sm.id == cp.id for sm in custom_styles):
                raise ValueError(
                    f"custom_profile {cp.id} 无对应 style_mode，请一并提交或删除"
                )


def custom_style_ids(registry: AgentRegistryData) -> set[str]:
    """返回 registry 中自定义风格 id 集合。"""
    return {sm.id for sm in registry.style_modes if _is_custom_style(sm)}


def assert_builtin_style_not_removed(
    old_registry: AgentRegistryData,
    new_style_modes: list[CustomStyleMode],
) -> None:
    """拒绝 PATCH 删除或覆盖内置风格定义。"""
    old_builtin_ids = {
        sm.id
        for sm in old_registry.style_modes
        if sm.builtin or is_builtin_style_mode(sm.id)
    }
    new_custom_ids = {sm.id for sm in new_style_modes if _is_custom_style(sm)}
    for bid in old_builtin_ids:
        if bid in new_custom_ids:
            raise ValueError(f"不可通过 PATCH 覆盖内置风格：{bid}")
