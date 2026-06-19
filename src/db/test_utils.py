"""Shared test utilities for InterChat test suites.

Provides mock SQLAlchemy session/result classes and helper builders
that both ``apps/bot`` and ``apps/payment`` can import.
"""

from __future__ import annotations

from typing import Any


class MockResult:
    """Mock for SQLAlchemy execute result."""

    def __init__(
        self,
        scalar: Any = None,
        scalars: list[Any] | None = None,
        tuples: list[Any] | None = None,
    ):
        self._scalar = scalar
        self._scalars = scalars or []
        self._tuples = tuples or []

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> MockScalars:
        if self._scalars:
            return MockScalars(self._scalars)
        if self._scalar is not None:
            return MockScalars([self._scalar])
        if self._tuples:
            return MockScalars([t[0] for t in self._tuples])
        return MockScalars([])

    def tuples(self) -> MockTuples:
        return MockTuples(self._tuples)

    def first(self) -> Any:
        if self._tuples:
            return self._tuples[0]
        return None

    def mappings(self) -> MockMappings:
        return MockMappings(self._tuples)


class MockMappings:
    """Mock for SQLAlchemy mappings result."""

    def __init__(self, items: list[Any]):
        self._items = items

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any:
        return self._items[0] if self._items else None


class MockScalars:
    """Mock for SQLAlchemy scalars result."""

    def __init__(self, items: list[Any]):
        self._items = items

    def all(self) -> list[Any]:
        return self._items

    def one(self) -> Any:
        if not self._items:
            raise ValueError('No rows returned')
        return self._items[0]

    def unique(self) -> MockScalars:
        return self


class MockTuples:
    """Mock for SQLAlchemy tuples result."""

    def __init__(self, items: list[Any]):
        self._items = items

    def __iter__(self):
        return iter(self._items)

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any:
        return self._items[0] if self._items else None


class MockSession:
    """Mock async session for repository unit tests.

    Tracks all session operations (add, delete, flush, commit) and
    optionally captures SQL statements for assertion.
    """

    def __init__(
        self,
        execute_results: dict[int, MockResult] | None = None,
        single_result: Any = None,
        capture_sql: bool = False,
    ):
        self._execute_count = 0
        self._execute_results = execute_results or {}
        self._single_result = single_result
        self._added: list[Any] = []
        self._deleted: list[Any] = []
        self._flushed = False
        self._committed = False
        self._capture_sql = capture_sql
        self.statements: list[Any] = []

    async def __aenter__(self) -> MockSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    async def execute(self, stmt: Any) -> MockResult:
        if self._capture_sql:
            self.statements.append(stmt)

        if self._single_result is not None:
            return MockResult(scalar=self._single_result)

        result = self._execute_results.get(self._execute_count, MockResult())
        self._execute_count += 1
        return result

    async def scalar(self, stmt: Any) -> Any:
        result = await self.execute(stmt)
        return result.scalar_one_or_none()

    async def scalars(self, stmt: Any) -> MockScalars:
        result = await self.execute(stmt)
        return result.scalars()

    async def get(self, model: Any, pk: Any) -> Any:
        result = await self.execute(None)
        return result.scalar_one_or_none()

    def add(self, obj: Any) -> None:
        self._added.append(obj)

    async def delete(self, obj: Any) -> None:
        self._deleted.append(obj)

    async def flush(self) -> None:
        self._flushed = True

    async def commit(self) -> None:
        self._committed = True

    @property
    def execute_count(self) -> int:
        return self._execute_count

    @property
    def added_objects(self) -> list[Any]:
        return self._added

    @property
    def deleted_objects(self) -> list[Any]:
        return self._deleted

    @property
    def was_flushed(self) -> bool:
        return self._flushed

    @property
    def was_committed(self) -> bool:
        return self._committed
