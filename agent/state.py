"""Agent 有限状态机；教师复核仍由后端保存，Agent 不自动批准结论。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentState(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    ANALYZING = "analyzing"
    VALIDATING = "validating"
    AWAITING_REVIEW = "awaiting_review"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"


ALLOWED_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.CREATED: frozenset({AgentState.PLANNING, AgentState.REPORTING, AgentState.FAILED}),
    AgentState.PLANNING: frozenset({AgentState.ANALYZING, AgentState.FAILED}),
    AgentState.ANALYZING: frozenset({AgentState.VALIDATING, AgentState.FAILED}),
    AgentState.VALIDATING: frozenset({AgentState.AWAITING_REVIEW, AgentState.FAILED}),
    AgentState.AWAITING_REVIEW: frozenset({AgentState.REPORTING, AgentState.FAILED}),
    AgentState.REPORTING: frozenset({AgentState.COMPLETED, AgentState.FAILED}),
    AgentState.COMPLETED: frozenset(),
    AgentState.FAILED: frozenset(),
}


class InvalidAgentTransition(ValueError):
    pass


@dataclass(slots=True)
class AgentWorkflow:
    state: AgentState = AgentState.CREATED

    def transition(self, target: AgentState) -> None:
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidAgentTransition(f"不允许 Agent 状态从 {self.state} 转到 {target}。")
        self.state = target

    def fail(self) -> None:
        if self.state not in (AgentState.COMPLETED, AgentState.FAILED):
            self.state = AgentState.FAILED
