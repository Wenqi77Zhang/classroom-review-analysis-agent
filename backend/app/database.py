"""异步数据库引擎、会话与事务边界。

负责人：成员 3。

事务边界定在**请求级**：一个 HTTP 请求 = 一个事务。理由是本项目的写操作几乎都要
连带写审计事件或任务事件（复核要同时落 `ReviewDecision` 与 `AuditEvent`，状态回写要
同时落 `ProcessingTask` 与 `TaskEvent`），分散提交会留下"改了业务但没留痕"的中间态，
而审计缺口是发布门禁盯着的东西。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import Settings, get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。Alembic 的 `target_metadata` 指向 `Base.metadata`。"""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or get_settings()
    return create_async_engine(
        settings.database_url.get_secret_value(),
        # 不打印 SQL：语句里会带上教师逐字稿内容与令牌等参数，日志不该收这些。
        echo=False,
        pool_pre_ping=True,  # Worker 空闲较久，连接可能已被数据库回收
        pool_size=10,
        max_overflow=5,
        pool_recycle=1800,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,  # 提交后仍可读响应字段，避免额外往返
            autoflush=False,
        )
    return _session_factory


async def session_scope() -> AsyncIterator[AsyncSession]:
    """请求级事务：正常结束提交，抛异常回滚。

    供 `dependencies.get_db` 使用。业务代码不自行 `commit()`，
    这样"写业务但漏写审计"无法通过测试。
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def dispose_engine() -> None:
    """应用关闭时释放连接池，供 FastAPI lifespan 调用。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_for_tests() -> None:
    """清空进程内缓存的引擎与会话工厂，供测试注入独立数据库。"""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
