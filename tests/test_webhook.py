"""LiveKit's webhook: signed the way LiveKit signs it, and what each event does to calls and streams.

Each event is posted to the real view the way LiveKit posts it: the body is the event's JSON, the
``Authorization`` header a JWT minted with the shared API key and secret whose ``sha256`` claim is
the body's hash. What it changes is read back from the database and from the subscriptions the
apps hold, running in-process on the channel layer.
"""

import base64
import hashlib

import pytest
from django.conf import settings
from django.test import AsyncClient
from django.urls import reverse
from google.protobuf.json_format import MessageToJson
from kante.context import HttpContext
from livekit.api import AccessToken
from livekit.protocol.models import ParticipantInfo, Room, TrackInfo
from livekit.protocol.webhook import WebhookEvent

from bridge.channels import participant_group
from bridge.graphql.mutations.call import call_group
from bridge.graphql.mutations.invite import invite_group
from bridge.graphql.mutations.stream import stream_group
from bridge.models import Call, CallInvite, User
from tests.support import AExecute, Subscribe, data_of

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]

ENSURE_CALL = "mutation ($input: EnsureCallInput!) { ensureCall(input: $input) { id } }"
INVITE = "mutation ($input: InviteToCallInput!) { inviteToCall(input: $input) { id } }"
DECLARE = "mutation ($input: DeclareStreamsInput!) { declareStreams(input: $input) { id key agent { id } } }"
CALL = "query ($id: ID!) { call(id: $id) { endedAt } }"

CALLS = "subscription { calls { create { id } update { id } ended { id endedAt } resumed { id endedAt } } }"
INVITES = "subscription { callInvites { create { id } delete } }"
PARTICIPANTS = "subscription ($call: ID!) { callParticipants(call: $call) { joined { identity name } left { identity } } }"
STREAMS = (
    "subscription { streams { create { id } live { id key } offline { id key } } }"
)

IMAGE = {"identifier": "@mikro/image", "object": 42}


def _signed(event: WebhookEvent, secret: str | None = None) -> tuple[str, str]:
    """The body and the Authorization header LiveKit would send for ``event``."""
    body = MessageToJson(event)
    token = AccessToken(
        settings.LIVEKIT["API_KEY"], secret or settings.LIVEKIT["API_SECRET"]
    )
    token.claims.sha256 = base64.b64encode(
        hashlib.sha256(body.encode()).digest()
    ).decode()
    return body, token.to_jwt()


async def _post(
    event: WebhookEvent, secret: str | None = None, body: str | None = None
) -> int:
    signed_body, auth = _signed(event, secret)
    response = await AsyncClient().post(
        reverse("livekit-webhook"),
        data=body if body is not None else signed_body,
        content_type="application/webhook+json",
        headers={"Authorization": auth},
    )
    return response.status_code


def _event(
    kind: str,
    room: str,
    participant: str | None = None,
    name: str = "",
    track: str | None = None,
) -> WebhookEvent:
    event = WebhookEvent(event=kind, room=Room(name=room), id=f"EV_{kind}_{room}")
    if participant is not None:
        event.participant.CopyFrom(
            ParticipantInfo(identity=participant, name=name, joined_at=1_700_000_000)
        )
    if track is not None:
        event.track.CopyFrom(TrackInfo(name=track, sid=f"TR_{track}"))
    return event


async def _call(aexecute: AExecute) -> str:
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not res.errors, res.errors
    assert res.data is not None
    return res.data["ensureCall"]["id"]


# --- signature ----------------------------------------------------------------------------


async def test_an_unsigned_or_forged_event_changes_nothing(aexecute: AExecute) -> None:
    call_id = await _call(aexecute)
    event = _event("room_finished", f"call-{call_id}")

    no_header = await AsyncClient().post(
        reverse("livekit-webhook"),
        data=MessageToJson(event),
        content_type="application/webhook+json",
    )
    assert no_header.status_code == 401
    assert await _post(event, secret="not-the-secret") == 401
    # Signed for another body: the hash no longer matches.
    assert (
        await _post(event, body=MessageToJson(_event("room_finished", "call-999999")))
        == 401
    )

    assert (await Call.objects.aget(id=call_id)).ended_at is None


# --- calls ----------------------------------------------------------------------------------


async def test_a_closed_room_ends_the_call_once_and_stops_its_invitations(
    aexecute: AExecute,
    authenticated_context: HttpContext,
    other_user_context: HttpContext,
    subscribe: Subscribe,
) -> None:
    call_id = await _call(aexecute)
    res = await aexecute(INVITE, {"input": {"call": call_id, "users": ["9"]}})
    assert not res.errors, res.errors
    assert res.data is not None
    invite = await CallInvite.objects.aget(call_id=call_id)
    invitee = await User.objects.aget(sub="9")

    organization = authenticated_context.request.organization
    calls = await subscribe(CALLS, {}, call_group(organization))
    invites = await subscribe(
        INVITES, {}, invite_group(organization, invitee), token="othertest"
    )

    assert await _post(_event("room_finished", f"call-{call_id}")) == 200

    ended = (await calls.next())["calls"]["ended"]
    assert ended["id"] == call_id and ended["endedAt"] is not None
    assert (await invites.next())["callInvites"]["delete"] == str(invite.pk)
    res = await aexecute(CALL, {"id": call_id})
    assert data_of(res)["call"]["endedAt"] == ended["endedAt"]

    # LiveKit retries a webhook it thinks was lost: the second one is news to nobody.
    assert await _post(_event("room_finished", f"call-{call_id}")) == 200
    assert await calls.nothing()
    assert await invites.nothing()


async def test_a_room_coming_back_resumes_an_ended_call_and_only_that(
    aexecute: AExecute, authenticated_context: HttpContext, subscribe: Subscribe
) -> None:
    call_id = await _call(aexecute)
    calls = await subscribe(
        CALLS, {}, call_group(authenticated_context.request.organization)
    )

    # A call's room starting the first time is not news: ``ensureCall`` announced it.
    assert await _post(_event("room_started", f"call-{call_id}")) == 200
    assert await calls.nothing()

    assert await _post(_event("room_finished", f"call-{call_id}")) == 200
    assert (await calls.next())["calls"]["ended"]["id"] == call_id

    assert await _post(_event("room_started", f"call-{call_id}")) == 200
    resumed = (await calls.next())["calls"]["resumed"]
    assert resumed == {"id": call_id, "endedAt": None}
    assert (await Call.objects.aget(id=call_id)).ended_at is None


async def test_watchers_of_a_call_hear_who_joins_and_leaves_it_and_no_other_call(
    aexecute: AExecute, subscribe: Subscribe
) -> None:
    call_id = await _call(aexecute)
    other_id = data_of(
        await aexecute(
            ENSURE_CALL,
            {"input": {"about": [{"identifier": "@mikro/image", "object": 7}]}},
        )
    )["ensureCall"]["id"]
    watcher = await subscribe(
        PARTICIPANTS, {"call": call_id}, participant_group(int(call_id))
    )

    assert (
        await _post(
            _event(
                "participant_joined",
                f"call-{call_id}",
                participant="user-1-abc",
                name="Ada",
            )
        )
        == 200
    )
    assert (await watcher.next())["callParticipants"] == {
        "joined": {"identity": "user-1-abc", "name": "Ada"},
        "left": None,
    }

    assert (
        await _post(
            _event("participant_joined", f"call-{other_id}", participant="user-9-xyz")
        )
        == 200
    )
    assert await watcher.nothing()

    assert (
        await _post(
            _event("participant_left", f"call-{call_id}", participant="user-1-abc")
        )
        == 200
    )
    assert (await watcher.next())["callParticipants"] == {
        "joined": None,
        "left": {"identity": "user-1-abc"},
    }


async def test_a_call_of_another_organization_cannot_be_watched(
    aexecute: AExecute, backend_stack: None
) -> None:
    from channels.layers import get_channel_layer
    from kante.context import UniversalRequest, WsContext
    from strawberry.channels import ChannelsConsumer
    from strawberry.http.temporal_response import TemporalResponse

    from lovekit_server.schema import schema

    call_id = await _call(aexecute)
    consumer = ChannelsConsumer()
    consumer.channel_layer = get_channel_layer()
    consumer.channel_name = await consumer.channel_layer.new_channel()
    context = WsContext(
        request=UniversalRequest(_extensions={"token": "stranger"}),
        response=TemporalResponse(),
        connection_params={"token": "stranger"},
        consumer=consumer,
    )
    subscription = await schema.subscribe(
        PARTICIPANTS, variable_values={"call": call_id}, context_value=context
    )
    results = [result async for result in subscription]
    assert results and results[0].errors
    assert participant_group(int(call_id)) not in consumer.channel_layer.groups


# --- streams --------------------------------------------------------------------------------


async def test_an_agents_tracks_make_its_streams_live_and_offline(
    aexecute: AExecute, authenticated_context: HttpContext, subscribe: Subscribe
) -> None:
    res = await aexecute(
        DECLARE, {"input": {"streams": [{"key": "camera"}, {"key": "detector"}]}}
    )
    assert not res.errors, res.errors
    assert res.data is not None
    streams = {stream["key"]: stream["id"] for stream in res.data["declareStreams"]}
    agent_id = res.data["declareStreams"][0]["agent"]["id"]
    room = f"agent-{agent_id}"
    publisher = f"agent-{agent_id}"
    events = await subscribe(
        STREAMS, {}, stream_group(authenticated_context.request.organization)
    )

    assert (
        await _post(
            _event("track_published", room, participant=publisher, track="camera")
        )
        == 200
    )
    assert (await events.next())["streams"]["live"] == {
        "id": streams["camera"],
        "key": "camera",
    }

    # A watcher in the agent's room publishing something makes nothing live.
    assert (
        await _post(
            _event(
                "track_published", room, participant="viewer-1-abc", track="detector"
            )
        )
        == 200
    )
    assert await events.nothing()

    assert (
        await _post(
            _event("track_unpublished", room, participant=publisher, track="camera")
        )
        == 200
    )
    assert (await events.next())["streams"]["offline"] == {
        "id": streams["camera"],
        "key": "camera",
    }

    # The agent leaving takes every stream of it offline.
    assert await _post(_event("participant_left", room, participant=publisher)) == 200
    offline = {(await events.next())["streams"]["offline"]["key"] for _ in streams}
    assert offline == {"camera", "detector"}


async def test_rooms_lovekit_does_not_own_are_acknowledged_and_ignored(
    aexecute: AExecute, authenticated_context: HttpContext, subscribe: Subscribe
) -> None:
    calls = await subscribe(
        CALLS, {}, call_group(authenticated_context.request.organization)
    )
    assert await _post(_event("room_finished", "somebody-elses-room")) == 200
    assert await _post(_event("egress_started", "call-1")) == 200
    assert await calls.nothing()
