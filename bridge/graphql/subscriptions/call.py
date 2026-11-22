"""Calls starting in the subscriber's organization, changing what they are about, ending and
coming back; and who comes and goes in one call."""

import logging
from collections.abc import AsyncGenerator

import strawberry
from kante.types import Info

from bridge import models, types
from bridge.channels import call_channel, call_participant_channel, participant_group
from bridge.graphql.mutations.call import call_group

logger = logging.getLogger(__name__)


@strawberry.type(
    description="A call starting in your organization, changing what it is about, ending, or coming back"
)
class CallEvent:
    create: types.Call | None = strawberry.field(
        default=None, description="A call someone else just started, which you can join"
    )
    update: types.Call | None = strawberry.field(
        default=None,
        description="A call that turned to something else; what it was about before is still in `about`",
    )
    ended: types.Call | None = strawberry.field(
        default=None,
        description="A call whose room closed: everyone left. `endedAt` says when",
    )
    resumed: types.Call | None = strawberry.field(
        default=None,
        description="A call that had ended and is live again: someone joined it",
    )


async def calls(self, info: Info) -> AsyncGenerator[CallEvent, None]:
    """The calls your organization starts, as they start, what they come to be about, and when they end.

    A start is never your own: you are already on your way in. A change, an end and a
    return are everyone's, yours included, so every open app shows the same calls.
    """
    request = info.context.request
    async for signal in call_channel.listen(info, [call_group(request.organization)]):
        call_id = next(
            (
                value
                for value in (
                    signal.create,
                    signal.update,
                    signal.ended,
                    signal.resumed,
                )
                if value is not None
            ),
            None,
        )
        if call_id is None:
            continue
        try:
            # Scoped again on the way out: the group name is not the only
            # thing between a call and another organization.
            call = await models.Call.objects.select_related("creator").aget(
                id=call_id, organization=request.organization
            )
        except models.Call.DoesNotExist:
            continue
        if signal.ended is not None:
            yield CallEvent(ended=call)
        elif signal.resumed is not None:
            yield CallEvent(resumed=call)
        elif signal.create is None:
            yield CallEvent(update=call)
        elif call.creator_id != request.user.id:
            yield CallEvent(create=call)


@strawberry.type(description="Someone joining or leaving a call")
class CallParticipantEvent:
    joined: types.CallParticipant | None = strawberry.field(
        default=None, description="Who just joined the call"
    )
    left: types.CallParticipant | None = strawberry.field(
        default=None, description="Who just left the call"
    )


async def call_participants(
    self, info: Info, call: strawberry.ID
) -> AsyncGenerator[CallParticipantEvent, None]:
    """Who joins and leaves this call, as LiveKit reports it. Read ``Call.participants`` once
    for who is in it now, then follow this."""
    request = info.context.request
    # A call of another organization does not exist for this caller.
    if not await models.Call.objects.filter(
        id=call, organization=request.organization
    ).aexists():
        raise ValueError(f"No call {call}")
    async for signal in call_participant_channel.listen(
        info, [participant_group(int(call))]
    ):
        if signal.call != int(call):
            continue
        participant = types.CallParticipant(
            identity=signal.identity, name=signal.name, joined_at=signal.joined_at
        )
        yield (
            CallParticipantEvent(left=participant)
            if signal.left
            else CallParticipantEvent(joined=participant)
        )
