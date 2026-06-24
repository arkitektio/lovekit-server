"""Integration tests for the stream / join mutations.

These mutations mint **real LiveKit JWT access tokens**; the tests decode them
with LiveKit's own `TokenVerifier` (using the dev keypair) and assert the grants
are scoped to the right room with the right permissions.
"""

import pytest
from django.conf import settings
from livekit.api import TokenVerifier

from bridge.models import Stream

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.docker]


ENSURE_SOLO_BROADCAST = """
mutation ($input: EnsureSoloBroadcastInput!) {
  ensureSoloBroadcast(input: $input) { id }
}
"""

ENSURE_STREAM = """
mutation ($input: EnsureStreamInput!) {
  ensureStream(input: $input)
}
"""

JOIN_BROADCAST = """
mutation ($input: JoinBroadcastInput!) {
  joinBroadcast(input: $input)
}
"""


def _verify(token: str):
    verifier = TokenVerifier(settings.LIVEKIT["API_KEY"], settings.LIVEKIT["API_SECRET"])
    return verifier.verify(token)


async def _make_solo_broadcast(aexecute, context=None):
    res = await aexecute(ENSURE_SOLO_BROADCAST, {"input": {"title": "Solo"}}, context=context)
    assert not res.errors, res.errors
    return res.data["ensureSoloBroadcast"]["id"]


async def test_ensure_stream_returns_scoped_token_and_creates_row(aexecute, livekit_client):
    bid = await _make_solo_broadcast(aexecute)

    res = await aexecute(ENSURE_STREAM, {"input": {"broadcast": bid}})
    assert not res.errors, res.errors

    token = res.data["ensureStream"]
    assert token

    # The token is a real, valid LiveKit JWT scoped to this broadcast's room.
    claims = _verify(token)
    assert claims.video.room == f"broadcast-{bid}"
    assert claims.video.room_join is True
    assert claims.identity.startswith("streamer-")

    # A Stream row was persisted for the broadcast.
    assert await Stream.objects.filter(broadcast_id=bid).aexists()


async def test_ensure_stream_rejects_non_owner(aexecute, other_user_context):
    # Owner (default authed user) creates the solo broadcast.
    bid = await _make_solo_broadcast(aexecute)

    # A different user tries to stream into it -> ownership assertion fails.
    res = await aexecute(ENSURE_STREAM, {"input": {"broadcast": bid}}, context=other_user_context)
    assert res.errors

    # No stream row was created for the intruder.
    assert not await Stream.objects.filter(broadcast_id=bid).aexists()


async def test_join_broadcast_returns_viewer_token(aexecute):
    bid = await _make_solo_broadcast(aexecute)

    res = await aexecute(JOIN_BROADCAST, {"input": {"broadcast": bid}})
    assert not res.errors, res.errors

    claims = _verify(res.data["joinBroadcast"])
    assert claims.video.room == f"broadcast-{bid}"
    assert claims.video.room_join is True
    # Viewers may subscribe but not publish.
    assert claims.video.can_publish is False
    assert claims.video.can_subscribe is True
    assert claims.identity.startswith("user-")
