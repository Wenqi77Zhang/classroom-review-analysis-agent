"""课堂分析 Skill；通用规则已实现，学科规则等待成员 4 提供。"""

from __future__ import annotations

from collections.abc import Callable

from agent.contracts import SkillSpec
from agent.skills import computer_ai, humanities


def load_domain_skills() -> dict[str, SkillSpec]:
    """Load only explicitly implemented member-4 skills; missing skills stay unavailable."""
    candidates: tuple[tuple[str, object, str], ...] = (
        ("computer_ai", computer_ai, "get_computer_ai_skill"),
        ("humanities", humanities, "get_humanities_skill"),
    )
    registry: dict[str, SkillSpec] = {}
    for expected_name, module, getter_name in candidates:
        getter = getattr(module, getter_name, None)
        if getter is None:
            continue
        if not isinstance(getter, Callable):
            raise TypeError(f"{getter_name} 必须是可调用对象。")
        skill = getter()
        if not isinstance(skill, SkillSpec) or skill.name != expected_name:
            raise ValueError(f"{getter_name} 必须返回 name={expected_name} 的 SkillSpec。")
        registry[expected_name] = skill
    return registry


__all__ = ["load_domain_skills"]
