"""Integration tests for the broadcast mutations.

Each test drives a GraphQL mutation through the real schema and then asserts
against the **live LiveKit server** (booted by the `backend_stack` fixture) that
the room the mutation claims to create actually exists.
"""

import pytest
from livekit.protocol.room import ListRoomsRequest

from bridge.models import SoloBroadcast, CollaborativeBroadcast, Streamer

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.docker]


ENSURE_SOLO_BROADCAST = """
mutation ($input: EnsureSoloBroadcastInput!) {
  ensureSoloBroadcast(input: $input) { id title }
}
"""

ENSURE_COLLABORATIVE_BROADCAST = """
mutation ($input: EnsureCollaborativeBroadcastInput!) {
  ensureCollaborativeBroadcast(input: $input) { id title }
}
"""


async def _room_names(livekit_client):
    rooms = await livekit_client.room.list_rooms(ListRoomsRequest())
    return {r.name for r in rooms.rooms}


async def test_ensure_solo_broadcast_creates_row_and_room(aexecute, livekit_client):
    res = await aexecute(ENSURE_SOLO_BROADCAST, {"input": {"title": "My Solo"}})
    assert not res.errors, res.errors

    bid = res.data["ensureSoloBroadcast"]["id"]
    assert res.data["ensureSoloBroadcast"]["title"] == "My Solo"

    # DB row exists.
    assert await SoloBroadcast.objects.filter(id=bid).aexists()

    # And the real LiveKit room was created with the broadcast's room id.
    assert f"broadcast-{bid}" in await _room_names(livekit_client)


async def test_ensure_solo_broadcast_is_idempotent(aexecute, livekit_client):
    first = await aexecute(ENSURE_SOLO_BROADCAST, {"input": {"title": "Same Title"}})
    second = await aexecute(ENSURE_SOLO_BROADCAST, {"input": {"title": "Same Title"}})
    assert not first.errors, first.errors
    assert not second.errors, second.errors

    # aget_or_create on (streamer, title) -> same broadcast both times.
    assert first.data["ensureSoloBroadcast"]["id"] == second.data["ensureSoloBroadcast"]["id"]
    assert await SoloBroadcast.objects.filter(title="Same Title").acount() == 1


async def test_ensure_collaborative_broadcast_creates_row_room_and_links_streamer(
    aexecute, livekit_client
):
    res = await aexecute(ENSURE_COLLABORATIVE_BROADCAST, {"input": {"title": "Team Stream"}})
    assert not res.errors, res.errors

    bid = res.data["ensureCollaborativeBroadcast"]["id"]
    broadcast = await CollaborativeBroadcast.objects.aget(id=bid)

    # The calling user's streamer is linked via the M2M.
    streamer = await Streamer.objects.aget(collaborative_broadcasts=broadcast)
    assert streamer is not None

    assert f"broadcast-{bid}" in await _room_names(livekit_client)
