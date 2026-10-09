"""Asking people into a call, and putting the invitation away.

An invite reaches the invitee's apps, every one they have open, through the
`callInvites` subscription; it is cleared for all of them when they dismiss
it or join the call from any device.
"""

import logging

from asgiref.sync import sync_to_async
from django.utils import timezone
from kante.types import Info

from bridge import inputs, models, types
from bridge.channel_signals import CallInviteSignal
from bridge.channels import call_invite_channel

logger = logging.getLogger(__name__)


def invite_group(organization, invitee: models.User) -> str:
    """The channel group one user's apps listen on. One definition, both sides.

    Spelled by hand rather than with ``org_group``: a channel-layer group name
    may hold only alphanumerics, hyphens, underscores and periods, and
    ``org_group`` joins its parts with colons.
    """
    organization_id = getattr(organization, "id", organization)
    return f"call_invites.org{organization_id}.user{invitee.id}"


@sync_to_async
def _create_invites(info: Info, input: inputs.InviteToCallInput) -> tuple[models.Call, list[models.CallInvite]]:
    request = info.context.request
    call = models.Call.objects.get(id=input.call, organization=request.organization)
    # Only people lovekit knows: an app that has talked to lovekit once. An
    # unknown sub has no app to ring, so it is skipped rather than invented.
    invitees = models.User.objects.filter(sub__in=[str(sub) for sub in input.users], iss=request.user.iss).exclude(id=request.user.id)
    created = []
    for invitee in invitees:
        invite, is_new = models.CallInvite.objects.get_or_create(
            call=call, invitee=invitee, dismissed_at=None, defaults={"inviter": request.user}
        )
        if is_new:
            created.append(invite)
    return call, created


async def invite_to_call(info: Info, input: inputs.InviteToCallInput) -> types.Call:
    """Ask these users into the call; their open apps ring."""
    call, created = await _create_invites(info, input)
    for invite in created:
        invitee = await models.User.objects.aget(id=invite.invitee_id)
        await call_invite_channel.abroadcast(
            CallInviteSignal(create=invite.id), [invite_group(call.organization_id, invitee)]
        )
    logger.info("Invited %d users to call %s", len(created), call.id)
    return call


@sync_to_async
def _dismiss(user, organization, invites) -> list[tuple[int, models.User]]:
    """Mark these pending invites dismissed; returns what to announce."""
    gone = []
    for invite in invites.filter(dismissed_at__isnull=True):
        invite.dismissed_at = timezone.now()
        invite.save(update_fields=["dismissed_at"])
        gone.append((invite.id, invite.invitee))
    return gone


async def _announce_dismissed(organization, gone: list[tuple[int, models.User]]) -> None:
    for invite_id, invitee in gone:
        await call_invite_channel.abroadcast(CallInviteSignal(delete=invite_id), [invite_group(organization, invitee)])


async def dismiss_call_invite(info: Info, input: inputs.DismissCallInviteInput) -> str:
    """Put an invitation away, on every device of the invitee."""
    request = info.context.request
    invites = models.CallInvite.objects.filter(id=input.id, invitee=request.user, call__organization=request.organization)
    gone = await _dismiss(request.user, request.organization, invites.select_related("invitee"))
    await _announce_dismissed(request.organization, gone)
    return str(input.id)


async def clear_invites_on_join(info: Info, call: models.Call) -> None:
    """Joining answers every pending invitation to this call for the joiner."""
    request = info.context.request
    invites = models.CallInvite.objects.filter(call=call, invitee=request.user).select_related("invitee")
    gone = await _dismiss(request.user, request.organization, invites)
    await _announce_dismissed(request.organization, gone)
