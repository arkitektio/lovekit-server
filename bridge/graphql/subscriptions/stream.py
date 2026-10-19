"""Agents in the subscriber's organization declaring, changing and dropping their streams."""

import logging
from typing import AsyncGenerator

import strawberry
from kante.types import Info

from bridge import models, types
from bridge.channels import stream_channel
from bridge.graphql.mutations.stream import stream_group

logger = logging.getLogger(__name__)


@strawberry.type(description="A stream an agent of your organization declared, changed or no longer offers")
class StreamEvent:
    create: types.Stream | None = strawberry.field(default=None, description="A stream an agent declared for the first time")
    update: types.Stream | None = strawberry.field(default=None, description="A stream whose title, kind or description changed")
    delete: strawberry.ID | None = strawberry.field(default=None, description="A stream its agent no longer offers")


async def streams(self, info: Info) -> AsyncGenerator[StreamEvent, None]:
    """The streams of your organization's agents, as they are declared, changed and dropped.

    Not whether they are live: that is LiveKit's, and ``Stream.live`` asks it.
    """
    request = info.context.request
    async for signal in stream_channel.listen(info, [stream_group(request.organization)]):
        if signal.delete is not None:
            yield StreamEvent(delete=strawberry.ID(str(signal.delete)))
            continue
        stream_id = signal.create if signal.create is not None else signal.update
        if stream_id is None:
            continue
        try:
            # Scoped again on the way out: the group name is not the only thing between a
            # stream and another organization.
            stream = await models.Stream.objects.select_related("agent").aget(id=stream_id, agent__organization=request.organization)
        except models.Stream.DoesNotExist:
            continue
        yield StreamEvent(create=stream) if signal.create is not None else StreamEvent(update=stream)
