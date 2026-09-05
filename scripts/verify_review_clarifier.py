"""Verify that the real local pre-upload Agent adapts to two teacher goals."""

from __future__ import annotations

import asyncio
import json

from agent.clarifier import ReviewClarificationAgent
from agent.providers.local import LocalModelProvider
from backend.app.config import Settings


async def main() -> int:
    settings = Settings()
    agent = ReviewClarificationAgent(
        LocalModelProvider(
            endpoint=settings.local_model_chat_completions_url,
            model=settings.local_model_name,
            reasoning_effort=settings.local_model_reasoning_effort,
        )
    )
    shared = {
        "course_name": "人工智能导论",
        "classroom_title": "什么是人工智能",
        "classroom_description": "用于本地验收的公开课课堂。",
    }
    structure = await agent.clarify(
        teacher_messages=["请分析整节课的概念讲解顺序是否清楚。"],
        trace_id="verify-review-structure",
        **shared,
    )
    wait_time = await agent.clarify(
        teacher_messages=["请分析教师每次提问后是否给学生留下了思考时间。"],
        trace_id="verify-review-wait-time",
        **shared,
    )
    structure_focus = structure.analysis_contract.focus_areas
    wait_focus = wait_time.analysis_contract.focus_areas
    if (
        structure.assistant_message == wait_time.assistant_message
        or structure.analysis_contract.goal == wait_time.analysis_contract.goal
        or structure_focus == wait_focus
    ):
        raise RuntimeError("本地模型没有针对两类教师目标生成可区分的澄清结果。")
    if structure.analysis_contract.confirmed or wait_time.analysis_contract.confirmed:
        raise RuntimeError("模型草案不得越过教师确认门禁。")
    print(
        json.dumps(
            {
                "status": "REAL_REVIEW_DIALOGUE_OK",
                "model": structure.model_name,
                "structure_focus": structure_focus,
                "wait_time_focus": wait_focus,
                "responses_are_distinct": True,
                "teacher_confirmation_required": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
