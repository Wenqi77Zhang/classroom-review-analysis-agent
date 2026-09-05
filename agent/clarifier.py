"""Bounded pre-upload Agent that turns teacher goals into a review contract draft."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent.providers.base import ModelProvider, ModelProviderError, ModelRequest
from backend.app.schemas.review_dialogue import (
    ModelReviewDialogue,
    ReviewDialogueResponse,
)

PROMPT_VERSION = "clarification-v1"
_PROMPT_PATH = Path(__file__).with_name("prompts") / "clarification.md"
_REQUIRED_EVIDENCE_RULE = "每条结论必须连接课堂原文、视频时间或课件页码之一"


def _language_hint(classroom_description: str | None) -> str:
    """Read the language marker written by the classroom creation form."""
    markers = {
        "zh": "Chinese",
        "mixed": "Chinese-English mixed",
        "en": "English",
    }
    if not classroom_description:
        return "unknown"
    marker = classroom_description.rsplit("·", maxsplit=1)[-1].strip().lower()
    return markers.get(marker, "unknown")


class ReviewClarificationAgent:
    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def clarify(
        self,
        *,
        teacher_messages: list[str],
        course_name: str,
        classroom_title: str,
        classroom_description: str | None,
        trace_id: str,
    ) -> ReviewDialogueResponse:
        schema = ModelReviewDialogue.model_json_schema(mode="serialization")
        context = {
            "trusted_classroom_context": {
                "course_name": course_name,
                "classroom_title": classroom_title,
                "classroom_description": classroom_description or "",
                "declared_language": _language_hint(classroom_description),
            },
            "untrusted_teacher_data": {"teacher_messages": teacher_messages},
            "turn_count": len(teacher_messages),
            "required_output_schema": schema,
        }
        request = ModelRequest(
            system_prompt=_PROMPT_PATH.read_text(encoding="utf-8"),
            user_prompt=json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            trace_id=trace_id,
            response_schema=schema,
        )
        response = await self._provider.generate_structured(request)
        try:
            generated = ModelReviewDialogue.model_validate(response.data)
            contract = generated.analysis_contract.to_analysis_contract()
        except (ValidationError, ValueError):
            repair_context: dict[str, Any] = {
                **context,
                "schema_repair": {
                    "required": True,
                    "instruction": "上次输出未通过结构校验。重新生成完整 JSON；不要复述无效输出。",
                },
            }
            repair = await self._provider.generate_structured(
                ModelRequest(
                    system_prompt=_PROMPT_PATH.read_text(encoding="utf-8"),
                    user_prompt=json.dumps(
                        repair_context,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    trace_id=trace_id,
                    response_schema=schema,
                )
            )
            try:
                generated = ModelReviewDialogue.model_validate(repair.data)
                contract = generated.analysis_contract.to_analysis_contract()
                response = repair
            except (ValidationError, ValueError) as repair_error:
                raise ModelProviderError("复盘 Agent 返回的分析契约未通过结构校验。") from repair_error
        evidence_requirements = list(contract.evidence_requirements)
        if not any("每条结论" in item and "连接" in item for item in evidence_requirements):
            if len(evidence_requirements) == 20:
                evidence_requirements[-1] = _REQUIRED_EVIDENCE_RULE
            else:
                evidence_requirements.append(_REQUIRED_EVIDENCE_RULE)
            contract = contract.model_copy(update={"evidence_requirements": evidence_requirements})

        reached_turn_limit = len(teacher_messages) >= 6
        clarification_needed = generated.clarification_needed and not reached_turn_limit
        assistant_message = generated.assistant_message
        if reached_turn_limit and generated.clarification_needed:
            # The model may still phrase its final turn as another question. The
            # server owns the bounded-loop policy, so keep the generated contract
            # but make the visible state truthful and actionable.
            assistant_message = "已根据现有信息形成分析契约草案；请核对并修改右侧内容。"
        return ReviewDialogueResponse(
            clarification_needed=clarification_needed,
            assistant_message=assistant_message,
            analysis_contract=contract,
            model_name=response.model_name,
            trace_id=trace_id,
        )
