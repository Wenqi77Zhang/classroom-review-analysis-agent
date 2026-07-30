"""使用合成课堂证据验证真实本地模型与项目 Agent 契约。

本脚本不会读取数据库、对象存储或真实课堂资料，也不需要任何 API 密钥。
它实际经过 AgentOrchestrator、LocalModelProvider、结构化输出校验和证据门禁，
适合在提交真实数据前确认本地模型链路可用。
"""

from __future__ import annotations

import asyncio
import json
import os
from time import perf_counter
from urllib.error import HTTPError
from uuid import UUID

from agent.contracts import AnalysisContract, AnalysisInput, CourseDomain, EvidenceItem
from agent.orchestrator import AgentOrchestrator
from agent.providers import ProviderRouter
from agent.providers.local import LocalModelProvider
from backend.app.schemas.analysis_report import EvidenceReference, EvidenceSourceType
from backend.app.schemas.task import PrivacyMode

TASK_ID = UUID("10000000-0000-4000-8000-000000000001")
OWNER_ID = UUID("10000000-0000-4000-8000-000000000002")
EVIDENCE_IDS = (
    UUID("10000000-0000-4000-8000-000000000101"),
    UUID("10000000-0000-4000-8000-000000000102"),
)


def _synthetic_input() -> AnalysisInput:
    """构造不含真实师生信息、但足以触发教学分析的证据。"""

    evidence = [
        EvidenceItem(
            id=EVIDENCE_IDS[0],
            task_id=TASK_ID,
            owner_id=OWNER_ID,
            reference=EvidenceReference(
                source_type=EvidenceSourceType.TRANSCRIPT,
                start_ms=120_000,
                end_ms=126_000,
                quote="教师：为什么这个算法会停止？（停顿约 0.8 秒）还是我来说明。",
            ),
            text="教师提出“为什么这个算法会停止”后停顿约 0.8 秒，"
            "未出现学生回答，随后教师立即开始讲解。",
            metadata={"synthetic": True},
        ),
        EvidenceItem(
            id=EVIDENCE_IDS[1],
            task_id=TASK_ID,
            owner_id=OWNER_ID,
            reference=EvidenceReference(
                source_type=EvidenceSourceType.TRANSCRIPT,
                start_ms=126_000,
                end_ms=136_000,
                quote="教师：因为循环变量最终会达到边界条件，我们继续。",
            ),
            text="教师直接给出边界条件解释并进入下一内容，"
            "该片段未记录追问、学生复述或理解检查。",
            metadata={"synthetic": True},
        ),
    ]
    return AnalysisInput(
        task_id=TASK_ID,
        owner_id=OWNER_ID,
        contract=AnalysisContract(
            goal="复盘教师提问后的等待时间与理解检查",
            focus_areas=["提问等待时间", "学生思考机会", "理解检查"],
            judgment_criteria=["事实与判断分层", "建议必须能由当前证据支持"],
            evidence_requirements=["每条结论必须引用所提供的逐字稿证据"],
            privacy_mode=PrivacyMode.LOCAL,
            course_domain=CourseDomain.GENERAL,
            confirmed=True,
        ),
        evidence=evidence,
        trace_id="local-model-synthetic-validation",
    )


async def _run() -> None:
    endpoint = os.getenv(
        "LOCAL_MODEL_CHAT_COMPLETIONS_URL",
        "http://127.0.0.1:11434/v1/chat/completions",
    )
    model = os.getenv("LOCAL_MODEL_NAME", "qwen3.5:4b")
    timeout_seconds = float(os.getenv("LOCAL_MODEL_VALIDATION_TIMEOUT_SECONDS", "300"))
    provider = LocalModelProvider(
        endpoint=endpoint,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    orchestrator = AgentOrchestrator(providers=ProviderRouter(local=provider))

    started = perf_counter()
    result = await orchestrator.analyze(_synthetic_input())
    elapsed_seconds = round(perf_counter() - started, 2)

    allowed_ids = set(EVIDENCE_IDS)
    conclusion_summaries: list[dict[str, object]] = []
    for conclusion in result.conclusions.conclusions:
        referenced_ids = {
            reference.segment_id
            for reference in conclusion.evidence_refs
            if reference.segment_id is not None
        }
        # 当前合成证据使用固定 evidence id，落到引用时 locator 不携带该 id；
        # 因而同时核对引用数量、时间定位和原始证据集合的非空性。
        if not conclusion.evidence_refs:
            raise RuntimeError("模型结论没有通过项目证据门禁。")
        if any(
            reference.start_ms is None or reference.end_ms is None
            for reference in conclusion.evidence_refs
        ):
            raise RuntimeError("模型结论缺少可跳转的时间定位。")
        if referenced_ids and not referenced_ids.issubset(allowed_ids):
            raise RuntimeError("模型结论引用了合成证据集合之外的 ID。")
        conclusion_summaries.append(
            {
                "type": conclusion.type.value,
                "content": conclusion.content,
                "evidence_count": len(conclusion.evidence_refs),
                "skill": conclusion.skill,
            }
        )

    summary = {
        "status": "LOCAL_MODEL_PROJECT_CONTRACT_OK",
        "synthetic_data_only": True,
        "model": result.model_name,
        "prompt_version": result.prompt_version,
        "skills": result.skills,
        "trace_id": result.trace_id,
        "elapsed_seconds": elapsed_seconds,
        "conclusion_count": len(conclusion_summaries),
        "conclusions": conclusion_summaries,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _local_http_error(error: BaseException) -> str | None:
    """只为本地合成验证提取 Ollama 的短错误说明，不输出请求或模型正文。"""

    current: BaseException | None = error
    while current is not None:
        if isinstance(current, HTTPError):
            try:
                payload = json.loads(current.read(4096))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return f"HTTP {current.code}"
            message = payload.get("error")
            if isinstance(message, dict):
                message = message.get("message")
            if isinstance(message, str):
                return message[:500]
            return f"HTTP {current.code}"
        current = current.__cause__
    return None


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except Exception as exc:
        detail = _local_http_error(exc)
        if detail:
            raise SystemExit(f"LOCAL_MODEL_VALIDATION_FAILED: {detail}") from exc
        raise
