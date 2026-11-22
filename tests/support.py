"""Types the fixtures of tests/conftest.py hand to the tests."""

import asyncio
import contextlib
from collections.abc import Awaitable, Mapping
from typing import Any, Protocol

from kante.context import Context, WsContext
from strawberry.types import ExecutionResult


class AExecute(Protocol):
    """The ``aexecute`` fixture: a GraphQL document run against the schema."""

    def __call__(
        self,
        query: str,
        variables: Mapping[str, object] | None = None,
        context: Context | None = None,
    ) -> Awaitable[ExecutionResult]: ...


class Subscribe(Protocol):
    """The ``subscribe`` fixture: a subscription as a static token, once it listens on ``group``."""

    def __call__(
        self,
        query: str,
        variables: dict[str, object],
        group: str,
        token: str = "test",
    ) -> Awaitable["Subscriber"]: ...


def data_of(result: ExecutionResult) -> dict[str, Any]:
    """``result.data``, asserted present (strawberry types it ``dict[str, Any] | None``)."""
    assert result.data is not None, result.errors
    return result.data


class Subscriber:
    """Drives one subscription from a single task, collecting what it yields.

    The AuthentikateExtension sets and resets context variables around the operation,
    which must happen in the same task; cancelling the task closes the subscription the
    way a client disconnect would.
    """

    def __init__(
        self, context: WsContext, query: str, variables: dict[str, object]
    ) -> None:
        self.context = context
        self.query = query
        self.variables = variables
        self.events: asyncio.Queue = asyncio.Queue()
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        from lovekit_server.schema import schema

        subscription = await schema.subscribe(
            self.query, variable_values=self.variables, context_value=self.context
        )
        if hasattr(subscription, "errors"):
            self.events.put_nowait(subscription)
            return
        async for result in subscription:
            self.events.put_nowait(result)

    async def next(self, timeout: float = 5) -> dict:
        result = await asyncio.wait_for(self.events.get(), timeout)
        assert not result.errors, result.errors
        return result.data

    async def nothing(self, timeout: float = 0.5) -> bool:
        """True when nothing more arrives within ``timeout``."""
        try:
            await asyncio.wait_for(self.events.get(), timeout)
        except TimeoutError:
            return True
        return False

    async def close(self) -> None:
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task
