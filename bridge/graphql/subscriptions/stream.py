"""Agents in the subscriber's organization declaring, changing and dropping their streams."""

import logging
from typing import AsyncGenerator

import strawberry
from kante.types import Info

from bridge import models, types
from bridge.channels import stream_channel
from bridge.graphql.mutations.stream import stream_group

logger = logging.getLogger(__name__)


@strawberry.type(description="A stream an agent of your organization declared, changed, no longer offers, or started or stopped publishing")
class StreamEvent:
    create: types.Stream | None = strawberry.field(default=None, description="A stream an agent declared for the first time")
    update: types.Stream | None = strawberry.field(default=None, description="A stream whose title, kind or description changed")
    delete: strawberry.ID | None = strawberry.field(default=None, description="A stream its agent no longer offers")
    live: types.Stream | None = strawberry.field(default=None, description="A stream its agent started publishing: it is live now")
    offline: types.Stream | None = strawberry.field(default=None, description="A stream its agent stopped publishing, or whose agent left: it is not live now")


async def streams(self, info: Info) -> AsyncGenerator[StreamEvent, None]:
    """The streams of your organization's agents, as they are declared, changed and dropped.

    And whether they are live, as LiveKit's webhook says it changes: read ``Stream.live``
    once, then follow ``live`` and ``offline``.
    """
    request = info.context.request
    async for signal in stream_channel.listen(info, [stream_group(request.organization)]):
        if signal.delete is not None:
            yield StreamEvent(delete=strawberry.ID(str(signal.delete)))
            continue
        stream_id = next((value for value in (signal.create, signal.update, signal.live, signal.offline) if value is not None), None)
        if stream_id is None:
            continue
        try:
            # Scoped again on the way out: the group name is not the only thing between a
            # stream and another organization.
            stream = await models.Stream.objects.select_related("agent").aget(id=stream_id, agent__organization=request.organization)
        except models.Stream.DoesNotExist:
            continue
        if signal.create is not None:
            yield StreamEvent(create=stream)
        elif signal.update is not None:
            yield StreamEvent(update=stream)
        elif signal.live is not None:
            yield StreamEvent(live=stream)
        else:
            yield StreamEvent(offline=stream)
