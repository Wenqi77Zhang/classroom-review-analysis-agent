"""Bounded, read-only production capacity probe for the public demo workspace."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from collections import Counter
from dataclasses import dataclass

import httpx

READ_PATHS = (
    "/api/backend-health",
    "/api/session/me",
    "/api/courses",
    "/api/tasks",
)


@dataclass(frozen=True)
class Sample:
    path: str
    status: int
    elapsed_ms: float


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


async def run_user(base_url: str, rounds: int, user_number: int) -> list[Sample]:
    samples: list[Sample] = []
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=httpx.Timeout(15.0),
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": f"classroom-capacity-acceptance/{user_number}"},
    ) as client:
        response = await client.post(
            "/api/session/demo",
            headers={"Origin": base_url, "Referer": f"{base_url}/login"},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"demo session {user_number} failed with HTTP {response.status_code}"
            )
        for _ in range(rounds):
            for path in READ_PATHS:
                started = time.perf_counter()
                response = await client.get(path)
                samples.append(
                    Sample(
                        path=path,
                        status=response.status_code,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
                )
    return samples


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--concurrency", type=int, choices=(1, 2, 4), required=True)
    parser.add_argument("--rounds", type=int, choices=range(1, 101), default=25)
    args = parser.parse_args()

    started = time.perf_counter()
    groups = await asyncio.gather(
        *(
            run_user(args.base_url.rstrip("/"), args.rounds, index + 1)
            for index in range(args.concurrency)
        )
    )
    samples = [sample for group in groups for sample in group]
    elapsed = time.perf_counter() - started
    latencies = [sample.elapsed_ms for sample in samples]
    status_counts = Counter(sample.status for sample in samples)
    path_summaries = {}
    for path in READ_PATHS:
        path_values = [sample.elapsed_ms for sample in samples if sample.path == path]
        path_summaries[path] = {
            "requests": len(path_values),
            "p50_ms": round(statistics.median(path_values), 2),
            "p95_ms": round(percentile(path_values, 0.95), 2),
            "max_ms": round(max(path_values), 2),
        }
    result = {
        "base_url": args.base_url.rstrip("/"),
        "concurrency": args.concurrency,
        "rounds_per_user": args.rounds,
        "request_count": len(samples),
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(len(samples) / elapsed, 2),
        "status_counts": dict(sorted(status_counts.items())),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "max_ms": round(max(latencies), 2),
        "paths": path_summaries,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if any(status < 200 or status >= 300 for status in status_counts):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run())
