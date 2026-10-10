"""Calls starting in the subscriber's organization, and changing what they are about."""

import logging
from typing import AsyncGenerator

import strawberry
from kante.types import Info

from bridge import models, types
from bridge.channels import call_channel
from bridge.graphql.mutations.call import call_group

logger = logging.getLogger(__name__)


@strawberry.type(description="A call starting in your organization, or changing what it is about")
class CallEvent:
    create: types.Call | None = strawberry.field(default=None, description="A call someone else just started, which you can join")
    update: types.Call | None = strawberry.field(default=None, description="A call that turned to something else; what it was about before is still in `about`")


async def calls(self, info: Info) -> AsyncGenerator[CallEvent, None]:
    """The calls your organization starts, as they start, and what they come to be about.

    A start is never your own: you are already on your way in. A change is
    everyone's, yours included, so every open app shows the same topics.
    """
    request = info.context.request
    async for signal in call_channel.listen(info, [call_group(request.organization)]):
        call_id = signal.create if signal.create is not None else signal.update
        if call_id is None:
            continue
        try:
            # Scoped again on the way out: the group name is not the only
            # thing between a call and another organization.
            call = await models.Call.objects.select_related("creator").aget(id=call_id, organization=request.organization)
        except models.Call.DoesNotExist:
            continue
        if signal.create is None:
            yield CallEvent(update=call)
        elif call.creator_id != request.user.id:
            yield CallEvent(create=call)
