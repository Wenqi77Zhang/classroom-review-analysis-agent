"""成员 5 主责的通用课堂分析 Skill。"""

from agent.contracts import SkillSpec

COMMON_SKILL = SkillSpec(
    name="common",
    version="1.0.0",
    instructions=(
        "分析课堂结构、目标衔接、讲解清晰度、提问与等待、例证和总结。"
        "事实只描述证据可观察内容；判断必须说明事实与标准的关系；"
        "建议必须可操作且不得超出已有证据。每条结论至少引用一个给定证据 ID。"
    ),
)


def get_common_skill() -> SkillSpec:
    return COMMON_SKILL.model_copy(deep=True)
