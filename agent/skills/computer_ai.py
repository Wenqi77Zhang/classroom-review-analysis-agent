"""Member 4's specialist rules for computer and AI classrooms."""

from agent.contracts import SkillSpec

COMPUTER_AI_SKILL = SkillSpec(
    name="computer_ai",
    version="1.0.0",
    instructions=(
        "分析计算机与人工智能课堂时，区分概念讲解、算法步骤、代码实现、运行演示和"
        "结果解释。涉及代码是否正确、界面是否运行或模型输出是否符合预期的结论，"
        "必须引用对应代码、课件页、视频片段或画面证据；只有口头提及不得当作运行"
        "成功。可以描述教师展示了什么、解释了什么，不得推断学生掌握程度、学习成效"
        "或未被证据直接展示的系统行为。每条建议必须指出它依据的原文或可定位视觉"
        "证据。"
    ),
)


def get_computer_ai_skill() -> SkillSpec:
    return COMPUTER_AI_SKILL.model_copy(deep=True)
