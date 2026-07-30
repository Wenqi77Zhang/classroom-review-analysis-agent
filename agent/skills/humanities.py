"""Member 4's specialist rules for humanities classrooms."""

from agent.contracts import SkillSpec

HUMANITIES_SKILL = SkillSpec(
    name="humanities",
    version="1.0.0",
    instructions=(
        "分析人文社科课堂时，区分材料原文、教师释义、论点、论据和课堂提问。涉及文本"
        "含义、概念界定、论证关系或史料使用的结论，必须引用逐字稿原文或带页码的"
        "课件材料；译文不能替代原文。只描述证据中明确表达的内容，不得推断教师或"
        "学生的立场、动机、情绪或身份，也不得把未出现的历史背景和价值判断补写成"
        "课堂事实。建议应回到具体原文、课件页或可定位课堂片段。"
    ),
)


def get_humanities_skill() -> SkillSpec:
    return HUMANITIES_SKILL.model_copy(deep=True)
