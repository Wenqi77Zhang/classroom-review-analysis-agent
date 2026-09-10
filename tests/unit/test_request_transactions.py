"""HTTP success must wait for commit; exceptions must reach the real transaction wrapper."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from backend.app import database
from backend.app.api.classrooms import Db
from backend.app.errors import AppError, StateConflictError


@pytest.mark.parametrize(
    ("mode", "expected_status", "commits", "rollbacks"),
    [("success", 201, 1, 0), ("commit_failure", 500, 1, 0),
     ("route_failure", 409, 0, 1), ("persist_failure_audit", 409, 1, 0)],
)
@pytest.mark.asyncio
async def test_real_dependency_transaction_lifecycle(monkeypatch, mode, expected_status, commits, rollbacks):
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    if mode == "commit_failure":
        session.commit.side_effect = RuntimeError("synthetic commit failure")

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(request, error):
        return JSONResponse({"error": "rejected"}, status_code=error.http_status)

    @app.post("/write", status_code=201)
    async def write(db: Db):
        assert db is session
        if mode == "route_failure":
            raise HTTPException(409)
        if mode == "persist_failure_audit":
            raise StateConflictError(commit_changes=True)
        return {"saved": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver") as client:
        response = await client.post("/write")
    assert response.status_code == expected_status
    if mode == "commit_failure":
        assert "saved" not in response.text
    assert session.commit.await_count == commits
    assert session.rollback.await_count == rollbacks
