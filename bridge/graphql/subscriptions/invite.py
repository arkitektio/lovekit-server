"""Invitations arriving for the subscriber, on whichever device this is."""

import logging
from typing import AsyncGenerator

import strawberry
from kante.types import Info

from bridge import models, types
from bridge.channels import call_invite_channel
from bridge.graphql.mutations.invite import invite_group

logger = logging.getLogger(__name__)


@strawberry.type(description="An invitation to a call arriving, or going away")
class CallInviteEvent:
    create: types.CallInvite | None = strawberry.field(default=None, description="A new invitation for you")
    delete: strawberry.ID | None = strawberry.field(default=None, description="An invitation that was dismissed or answered, here or on another device")


async def call_invites(self, info: Info) -> AsyncGenerator[CallInviteEvent, None]:
    """Your invitations as they come and go. Every open app of yours gets them."""
    request = info.context.request
    group = invite_group(request.organization, request.user)
    async for signal in call_invite_channel.listen(info, [group]):
        if signal.create is not None:
            try:
                invite = await models.CallInvite.objects.select_related("call", "inviter", "invitee").aget(
                    id=signal.create, invitee=request.user
                )
            except models.CallInvite.DoesNotExist:
                continue
            yield CallInviteEvent(create=invite)
        elif signal.delete is not None:
            yield CallInviteEvent(delete=str(signal.delete))
