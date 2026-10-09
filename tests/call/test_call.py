"""Integration tests for calls: a LiveKit room about some structures.

Each test drives the schema and then asserts against the **live LiveKit
server** (booted by the `backend_stack` fixture) that the room the mutation
claims to create exists, and that the token it mints opens that room.
"""

import jwt
import pytest
from livekit.protocol.room import ListRoomsRequest

from bridge.models import Call

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.docker]


ENSURE_CALL = """
mutation ($input: EnsureCallInput!) {
  ensureCall(input: $input) { id title roomName about { identifier object } participants { identity } }
}
"""

JOIN_CALL = """
mutation ($input: JoinCallInput!) {
  joinCall(input: $input)
}
"""

CALLS_ABOUT = """
query ($about: StructureInput!, $live: Boolean) {
  calls(filters: { about: $about, live: $live }) { id title participantCount }
}
"""

IMAGE = {"identifier": "@mikro/image", "object": 42}


async def _room_names(livekit_client):
    rooms = await livekit_client.room.list_rooms(ListRoomsRequest())
    return {r.name for r in rooms.rooms}


async def test_ensure_call_creates_row_and_room(aexecute, livekit_client):
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not res.errors, res.errors

    call = res.data["ensureCall"]
    assert call["title"] == "Call about @mikro/image 42"
    assert call["about"] == [IMAGE]
    assert call["roomName"] == f"call-{call['id']}"
    assert call["participants"] == []

    assert await Call.objects.filter(id=call["id"]).aexists()
    assert call["roomName"] in await _room_names(livekit_client)


async def test_ensure_call_reuses_the_live_call_about_the_same_thing(aexecute):
    first = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE], "title": "Look at this"}})
    second = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not first.errors, first.errors
    assert not second.errors, second.errors

    # The room from the first call is still up (empty timeout), so the second
    # press lands in it rather than opening a room beside it.
    assert first.data["ensureCall"]["id"] == second.data["ensureCall"]["id"]
    assert second.data["ensureCall"]["title"] == "Look at this"


async def test_ensure_call_about_something_else_is_another_call(aexecute):
    first = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    other = await aexecute(ENSURE_CALL, {"input": {"about": [{"identifier": "@mikro/image", "object": 43}]}})
    assert first.data["ensureCall"]["id"] != other.data["ensureCall"]["id"]


async def test_ensure_call_needs_a_subject(aexecute):
    res = await aexecute(ENSURE_CALL, {"input": {"about": []}})
    assert res.errors


async def test_join_call_mints_a_publishing_token_for_the_room(aexecute):
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call = created.data["ensureCall"]

    res = await aexecute(JOIN_CALL, {"input": {"call": call["id"]}})
    assert not res.errors, res.errors

    claims = jwt.decode(res.data["joinCall"], options={"verify_signature": False})
    assert claims["video"]["room"] == call["roomName"]
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublish"] is True
    assert claims["video"]["canSubscribe"] is True
    assert claims["sub"].startswith("user-")
    # What the others see: the preferred username, never the iss_sub artifact.
    from authentikate.models import User

    user = await User.objects.aget(sub="1")
    assert claims["name"] == (user.first_name or user.username)
    assert claims["name"] != "static_issuer_1" or not user.first_name


async def test_join_call_twice_gives_two_identities(aexecute):
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = created.data["ensureCall"]["id"]
    first = await aexecute(JOIN_CALL, {"input": {"call": call_id}})
    second = await aexecute(JOIN_CALL, {"input": {"call": call_id}})
    identity = lambda token: jwt.decode(token, options={"verify_signature": False})["sub"]  # noqa: E731
    # A second window joins beside the first instead of kicking it out.
    assert identity(first.data["joinCall"]) != identity(second.data["joinCall"])


async def test_calls_about_a_structure_and_their_liveness(aexecute):
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = created.data["ensureCall"]["id"]

    live = await aexecute(CALLS_ABOUT, {"about": IMAGE, "live": True})
    assert not live.errors, live.errors
    assert [c["id"] for c in live.data["calls"]] == [call_id]
    assert live.data["calls"][0]["participantCount"] == 0

    nobody = await aexecute(CALLS_ABOUT, {"about": {"identifier": "@mikro/image", "object": 999}})
    assert nobody.data["calls"] == []

    down = await aexecute(CALLS_ABOUT, {"about": IMAGE, "live": False})
    assert down.data["calls"] == []


async def test_calls_are_scoped_to_the_organization(aexecute, authenticated_context):
    """A call of another organization does not exist for the caller."""
    from tests.conftest import _make_context

    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = created.data["ensureCall"]["id"]

    from asgiref.sync import sync_to_async

    # The extension re-resolves the organization from the token, so another
    # organization needs its own static token (see settings_test).
    stranger = await sync_to_async(_make_context)(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )

    listed = await aexecute(CALLS_ABOUT, {"about": IMAGE}, context=stranger)
    assert not listed.errors, listed.errors
    assert listed.data["calls"] == []

    joined = await aexecute(JOIN_CALL, {"input": {"call": call_id}}, context=stranger)
    assert joined.errors
