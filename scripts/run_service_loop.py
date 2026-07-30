"""Repeat the existing one-shot Worker or Agent entrypoint without exposing secrets in argv."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Sequence


def service_command(service: str) -> list[str]:
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    if service == "worker":
        return [
            sys.executable,
            "-m",
            "worker.runner",
            "--api-base-url",
            backend_url,
        ]
    if service == "agent":
        return [sys.executable, "-m", "agent.runner", "--backend-url", backend_url]
    raise ValueError(f"未知服务：{service}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="循环运行一次性 Worker/Agent 领取入口。")
    parser.add_argument("service", choices=("worker", "agent"))
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=float(os.getenv("SERVICE_POLL_INTERVAL_SECONDS", "5")),
    )
    args = parser.parse_args(argv)
    if not 0.5 <= args.interval_seconds <= 300:
        parser.error("interval-seconds 必须在 0.5 到 300 之间。")

    command = service_command(args.service)
    stopping = threading.Event()
    current: subprocess.Popen[bytes] | None = None

    def stop_handler(_signum: int, _frame: object) -> None:
        stopping.set()
        if current is not None and current.poll() is None:
            current.terminate()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    try:
        while not stopping.is_set():
            current = subprocess.Popen(command)
            returncode = current.wait()
            current = None
            if stopping.is_set():
                break
            if returncode != 0:
                print(
                    f"{args.service} 本轮退出码 {returncode}；"
                    "等待后继续，错误详情由任务状态和 Trace ID 回溯。",
                    file=sys.stderr,
                    flush=True,
                )
            stopping.wait(args.interval_seconds)
    except KeyboardInterrupt:
        stopping.set()
    finally:
        if current is not None and current.poll() is None:
            current.terminate()
            try:
                current.wait(timeout=10)
            except subprocess.TimeoutExpired:
                current.kill()
                current.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
