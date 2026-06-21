# Copyright (C) 2026 dev-737
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://gnu.org>.

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction, async_sessionmaker, create_async_engine

from .logger import logger

_current_session: ContextVar[AsyncSession | None] = ContextVar('_current_session', default=None)

# Semaphore that caps the number of concurrent DB sessions process-wide.
# Prevents unbounded background-task fanout from saturating the connection
# pool and hitting PostgreSQL's server-side max_connections limit.
# Override via DB_MAX_CONCURRENT_SESSIONS env var.


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning('Invalid integer for %s=%r, using default %s', name, raw, default)
        return default


_session_semaphore: asyncio.Semaphore | None = None


def _get_session_semaphore() -> asyncio.Semaphore:
    global _session_semaphore
    if _session_semaphore is None:
        limit = _env_int('DB_MAX_CONCURRENT_SESSIONS', 25)
        _session_semaphore = asyncio.Semaphore(limit)
        logger.info(
            'DB session semaphore initialised (limit=%s, pool_size=%s, max_overflow=%s)',
            limit,
            _env_int('DB_POOL_SIZE', 15),
            _env_int('DB_MAX_OVERFLOW', 10),
        )
    return _session_semaphore


def get_current_session() -> AsyncSession | None:
    """Return the active UOW session for the calling async task, or *None*."""
    return _current_session.get()


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._tx: AsyncSessionTransaction | None = None
        self._on_commit: list[Callable[[], Awaitable[None]]] = []
        self._semaphore_held: bool = False

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError('UnitOfWork not entered')
        return self._session

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._on_commit.append(callback)

    async def __aenter__(self) -> UnitOfWork:
        try:
            await asyncio.wait_for(
                _get_session_semaphore().acquire(),
                timeout=30.0,
            )
            self._semaphore_held = True
        except TimeoutError:
            limit = _env_int('DB_MAX_CONCURRENT_SESSIONS', 25)
            logger.error(
                'DB session semaphore timeout after 30s — limit is %s concurrent sessions. '
                'Consider increasing DB_MAX_CONCURRENT_SESSIONS or checking for '
                'long-running transactions blocking pool connections.',
                limit,
            )
            raise
        self._session = self._session_factory()
        self._tx = await self._session.begin()
        _current_session.set(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._tx is None or self._session is None:
                raise RuntimeError('UnitOfWork exit without enter')

            callbacks = self._on_commit
            self._on_commit = []

            try:
                if exc_type:
                    await self._tx.rollback()
                else:
                    await self._tx.commit()
            finally:
                await self._session.close()
                self._session = None
                self._tx = None
                _current_session.set(None)

            if not exc_type:
                for cb in callbacks:
                    try:
                        await cb()
                    except Exception:
                        logger.exception('UnitOfWork post-commit callback failed')
        finally:
            if self._semaphore_held:
                _get_session_semaphore().release()
                self._semaphore_held = False


class Database:
    def __init__(self, database_url: str | None = os.getenv('DATABASE_URL')) -> None:
        self.database_url: str | None = database_url
        if not self.database_url:
            raise ValueError('DATABASE_URL environment variable is required')

        pool_size = max(1, _env_int('DB_POOL_SIZE', 15))
        max_overflow = max(0, _env_int('DB_MAX_OVERFLOW', 10))
        pool_timeout = max(1, _env_int('DB_POOL_TIMEOUT', 5))
        pool_recycle = max(30, _env_int('DB_POOL_RECYCLE', 300))
        pool_use_lifo = os.getenv('DB_POOL_USE_LIFO', 'false').strip().lower() in ('true', '1', 'yes')
        connect_timeout = _env_int('DB_CONNECT_TIMEOUT', 10)
        command_timeout = _env_int('DB_COMMAND_TIMEOUT', 30)

        try:
            connect_args: dict[str, object] = {
                'timeout': connect_timeout,
                'command_timeout': command_timeout,
            }
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,
                pool_recycle=pool_recycle,
                pool_timeout=pool_timeout,
                pool_use_lifo=pool_use_lifo,
                pool_logging_name='interchat.pool',
                connect_args=connect_args,
            )
            self.async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                class_=AsyncSession,
            )
            logger.info(
                'Database engine creation successful '
                '(pool_size=%s, max_overflow=%s, pool_timeout=%ss, pool_recycle=%ss, pool_use_lifo=%s, '
                'connect_timeout=%ss, command_timeout=%ss)',
                pool_size,
                max_overflow,
                pool_timeout,
                pool_recycle,
                pool_use_lifo,
                connect_timeout,
                command_timeout,
            )
        except Exception as e:
            logger.error(f'Failed to create database engine: {e}')
            raise ValueError('Invalid DATABASE_URL or connection options') from e

    async def dispose(self) -> None:
        """Dispose the engine and release all pooled connections."""
        await self.engine.dispose()

    async def health_check(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text('SELECT 1'))
            return True
        except Exception as e:
            logger.error(f'Health check failed: {e}')
            return False

    def uow(self) -> UnitOfWork:
        """Return a new UnitOfWork manager for handling transactions explicitly."""
        return UnitOfWork(self.async_session)


# Global database singleton
_db: Database | None = None


def init_database(database_url: str | None = None) -> Database:
    """Initialise the global :class:`Database` singleton.

    Parameters
    ----------
    database_url:
        Connection string.  Falls back to the ``DATABASE_URL`` env-var when
        *None*.
    """
    global _db
    _db = Database(database_url)
    return _db


def get_db() -> Database:
    """Return the initialised :class:`Database` singleton.

    Raises
    ------
    RuntimeError
        If :func:`init_database` has not been called yet.
    """
    if _db is None:
        raise RuntimeError('Database not initialized. Call init_database() first.')
    return _db
