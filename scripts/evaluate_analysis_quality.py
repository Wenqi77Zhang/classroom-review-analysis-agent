"""Run a frozen AnalysisInput through the real Agent, without database writes.

Outputs are local evaluation artifacts, not proof of teacher acceptance. Use
--include-content only for inputs whose classroom content may be saved locally;
never commit those artifacts or use a cloud endpoint for private classroom data.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.contracts import AnalysisInput
from agent.observability.tracing import InMemoryTraceSink
from agent.orchestrator import PROMPT_VERSION, AgentOrchestrator, AgentRunError
from agent.providers import ProviderRouter
from agent.providers.base import ModelProvider, ModelRequest, ModelResponse
from agent.providers.local import LocalModelProvider
from agent.skills import load_domain_skills


class RecordingProvider(ModelProvider):
    def __init__(self, delegate: LocalModelProvider, *, include_content: bool) -> None:
        self.delegate = delegate
        self.include_content = include_content
        self.calls: list[dict] = []

    @property
    def model_name(self) -> str:
        return self.delegate.model_name

    async def generate_structured(self, request: ModelRequest) -> ModelResponse:
        response = await self.delegate.generate_structured(request)
        record = {
            "latency_ms": response.latency_ms,
            "usage": response.usage,
            "prompt_chars": len(request.system_prompt) + len(request.user_prompt),
            "prompt_sha256": hashlib.sha256(
                (request.system_prompt + "\n" + request.user_prompt).encode()
            ).hexdigest(),
        }
        if self.include_content:
            record["response"] = response.data
        self.calls.append(record)
        return response


async def evaluate(args: argparse.Namespace) -> dict:
    raw = args.input.read_bytes()
    analysis_input = AnalysisInput.model_validate_json(raw)
    provider = RecordingProvider(
        LocalModelProvider(
            endpoint=args.endpoint, model=args.model,
            timeout_seconds=600, max_tokens=args.max_tokens,
        ),
        include_content=args.include_content,
    )
    sink = InMemoryTraceSink()
    orchestrator = AgentOrchestrator(
        providers=ProviderRouter(local=provider),
        skill_registry=load_domain_skills(), trace_sink=sink,
    )
    record = {
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "model": args.model,
        "label": args.label,
        "started_at": datetime.now(UTC).isoformat(),
        "evidence_count": len(analysis_input.evidence),
        "semantic_support": "requires_review",
    }
    start = perf_counter()
    try:
        result = await orchestrator.analyze(analysis_input)
        record.update(status="succeeded", conclusion_count=len(result.conclusions.conclusions))
        if args.include_content:
            record["result"] = result.model_dump(mode="json")
    except AgentRunError as exc:
        record.update(status="failed", error_code=exc.code.value)
    record["elapsed_seconds"] = round(perf_counter() - start, 3)
    record["calls"] = provider.calls
    record["events"] = [
        {"name": event.name, "attributes": event.attributes} for event in sink.events
    ]
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="qwen3.5:0.8b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/v1/chat/completions")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--label", required=True)
    parser.add_argument("--include-content", action="store_true")
    args = parser.parse_args()
    # Never overwrite a baseline or follow an existing output symlink.
    descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        result = asyncio.run(evaluate(args))
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps({key: result[key] for key in (
        "label", "status", "input_sha256", "elapsed_seconds"
    )}))


if __name__ == "__main__":
    main()
