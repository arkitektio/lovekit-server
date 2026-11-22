"""What LiveKit tells lovekit about its rooms, as it happens.

LiveKit posts a webhook for every room and participant change. Each is signed with
the API key and secret lovekit already shares with it (a JWT whose ``sha256`` claim
is the body's hash), so the view checks that before it reads anything. Then the news
goes out on the same channels the mutations broadcast on:

- a call's room closing ends the call (``Call.ended_at``, ``CallEvent.ended``), and
  the call's pending invitations stop ringing (``CallInviteEvent.delete``);
- a call's room coming up again after it ended resumes it (``CallEvent.resumed``);
- someone joining or leaving a call's room is news for whoever watches that call
  (``callParticipants``);
- an agent publishing or unpublishing a track, or leaving its room, is a stream going
  live or offline (``StreamEvent.live`` / ``offline``).

Rooms are told apart by name, the way everything else here does it: ``call-<id>`` is a
call, ``agent-<id>`` an agent. Anything else (and events lovekit has no use for) is
acknowledged and ignored, so LiveKit does not retry it.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from livekit.api import TokenVerifier, WebhookReceiver
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.webhook import WebhookEvent

from bridge import models
from bridge.channel_signals import (
    CallInviteSignal,
    CallParticipantSignal,
    CallSignal,
    StreamSignal,
)
from bridge.channels import (
    call_channel,
    call_invite_channel,
    call_participant_channel,
    participant_group,
    stream_channel,
)
from bridge.graphql.mutations.call import call_group
from bridge.graphql.mutations.invite import invite_group
from bridge.graphql.mutations.stream import stream_group

logger = logging.getLogger(__name__)


def _room_id(room_name: str, prefix: str) -> int | None:
    """The id in a room name of the form ``<prefix>-<id>``, or None for any other room."""
    head = f"{prefix}-"
    if room_name.startswith(head) and room_name[len(head) :].isdigit():
        return int(room_name[len(head) :])
    return None


def _receiver() -> WebhookReceiver:
    return WebhookReceiver(
        TokenVerifier(settings.LIVEKIT["API_KEY"], settings.LIVEKIT["API_SECRET"])
    )


# --- calls ---------------------------------------------------------------------------------


async def _call_ended(call_id: int) -> None:
    """The call's room closed: record it once, announce it, and stop its invitations ringing."""
    now = timezone.now()
    # Only an open call ends: a retried webhook changes nothing and announces nothing.
    changed = await models.Call.objects.filter(
        id=call_id, ended_at__isnull=True
    ).aupdate(ended_at=now)
    if not changed:
        return
    call = await models.Call.objects.aget(id=call_id)
    await call_channel.abroadcast(
        CallSignal(ended=call.id), [call_group(call.organization_id)]
    )
    # Pending invitations to a call that is over are moot (``myCallInvites`` already leaves
    # them out); every device still ringing hears that they are gone.
    async for invite in models.CallInvite.objects.filter(
        call_id=call_id, dismissed_at__isnull=True
    ).select_related("invitee"):
        await call_invite_channel.abroadcast(
            CallInviteSignal(delete=invite.id),
            [invite_group(call.organization_id, invite.invitee)],
        )
    logger.info("Call %s ended", call_id)


async def _call_started(call_id: int) -> None:
    """The call's room came up. Only news when the call had ended: a new call was announced when it started."""
    changed = await models.Call.objects.filter(
        id=call_id, ended_at__isnull=False
    ).aupdate(ended_at=None)
    if not changed:
        return
    call = await models.Call.objects.aget(id=call_id)
    await call_channel.abroadcast(
        CallSignal(resumed=call.id), [call_group(call.organization_id)]
    )
    logger.info("Call %s resumed", call_id)


async def _participant(call_id: int, participant: ParticipantInfo, left: bool) -> None:
    signal = CallParticipantSignal(
        call=call_id,
        identity=participant.identity,
        name=participant.name,
        joined_at=participant.joined_at,
        left=left,
    )
    await call_participant_channel.abroadcast(signal, [participant_group(call_id)])


# --- agents --------------------------------------------------------------------------------


async def _stream_signal(agent_id: int, key: str | None, live: bool) -> None:
    """Announce the agent's stream ``key`` (every stream, when None) going live or offline."""
    streams = models.Stream.objects.filter(agent_id=agent_id).select_related("agent")
    if key is not None:
        streams = streams.filter(key=key)
    async for stream in streams:
        signal = (
            StreamSignal(live=stream.id) if live else StreamSignal(offline=stream.id)
        )
        await stream_channel.abroadcast(
            signal, [stream_group(stream.agent.organization_id)]
        )


def _is_publisher(agent_id: int, participant: ParticipantInfo) -> bool:
    # Only the agent's own publisher makes a stream live; a watcher in the room does not.
    return participant.identity == f"agent-{agent_id}"


# --- dispatch ------------------------------------------------------------------------------


async def handle(event: WebhookEvent) -> None:
    """Act on one verified webhook event."""
    room_name = event.room.name
    call_id = _room_id(room_name, "call")
    agent_id = _room_id(room_name, "agent")

    if call_id is not None:
        if event.event == "room_finished":
            await _call_ended(call_id)
        elif event.event == "room_started":
            await _call_started(call_id)
        elif event.event in ("participant_joined", "participant_left"):
            await _participant(
                call_id, event.participant, left=event.event == "participant_left"
            )
        return

    if agent_id is not None:
        if event.event == "room_finished":
            await _stream_signal(agent_id, None, live=False)
        elif event.event == "participant_left" and _is_publisher(
            agent_id, event.participant
        ):
            await _stream_signal(agent_id, None, live=False)
        elif event.event in ("track_published", "track_unpublished") and _is_publisher(
            agent_id, event.participant
        ):
            await _stream_signal(
                agent_id, event.track.name, live=event.event == "track_published"
            )


@csrf_exempt
@require_POST
async def livekit_webhook(request: HttpRequest) -> HttpResponse:
    """The endpoint LiveKit posts its webhooks to (``webhook.urls`` in its config)."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return HttpResponse("missing authorization", status=401)
    try:
        event = _receiver().receive(request.body.decode(), token)
    except Exception as error:  # noqa: BLE001 - the receiver raises bare Exceptions for a bad signature or hash
        logger.warning("Refused a LiveKit webhook: %s", error)
        return HttpResponse("invalid signature", status=401)
    await handle(event)
    return HttpResponse(status=200)
