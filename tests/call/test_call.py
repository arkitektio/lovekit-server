"""Integration tests for calls: a LiveKit room about some structures.

Each test drives the schema and then asserts against the **live LiveKit
server** (booted by the `backend_stack` fixture) that the room the mutation
claims to create exists, and that the token it mints opens that room.
"""

import jwt
import pytest
from kante.context import HttpContext
from livekit.api import LiveKitAPI
from livekit.protocol.room import ListRoomsRequest

from bridge.models import Call
from tests.support import AExecute, data_of

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]


ENSURE_CALL = """
mutation ($input: EnsureCallInput!) {
  ensureCall(input: $input) { id title roomName about { identifier object } participants { identity } }
}
"""

JOIN_CALL = """
mutation ($input: JoinCallInput!) {
  joinCall(input: $input) { transport credential }
}
"""

CALLS_ABOUT = """
query ($about: StructureInput!, $live: Boolean) {
  calls(filters: { about: $about, live: $live }) { id title participantCount }
}
"""

IMAGE = {"identifier": "@mikro/image", "object": 42}


async def _room_names(livekit_client: LiveKitAPI) -> set[str]:
    rooms = await livekit_client.room.list_rooms(ListRoomsRequest())
    return {r.name for r in rooms.rooms}


async def test_ensure_call_creates_row_and_room(
    aexecute: AExecute, livekit_client: LiveKitAPI
) -> None:
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not res.errors, res.errors
    assert res.data is not None

    call = res.data["ensureCall"]
    assert call["title"] == "Call about @mikro/image 42"
    assert call["about"] == [IMAGE]
    assert call["roomName"] == f"call-{call['id']}"
    assert call["participants"] == []

    assert await Call.objects.filter(id=call["id"]).aexists()
    assert call["roomName"] in await _room_names(livekit_client)


async def test_ensure_call_reuses_the_live_call_about_the_same_thing(
    aexecute: AExecute,
) -> None:
    first = await aexecute(
        ENSURE_CALL, {"input": {"about": [IMAGE], "title": "Look at this"}}
    )
    second = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not first.errors, first.errors
    assert first.data is not None
    assert not second.errors, second.errors
    assert second.data is not None

    # The room from the first call is still up (empty timeout), so the second
    # press lands in it rather than opening a room beside it.
    assert first.data["ensureCall"]["id"] == second.data["ensureCall"]["id"]
    assert second.data["ensureCall"]["title"] == "Look at this"


async def test_ensure_call_about_something_else_is_another_call(
    aexecute: AExecute,
) -> None:
    first = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    other = await aexecute(
        ENSURE_CALL,
        {"input": {"about": [{"identifier": "@mikro/image", "object": 43}]}},
    )
    assert data_of(first)["ensureCall"]["id"] != data_of(other)["ensureCall"]["id"]


async def test_ensure_call_needs_a_subject(aexecute: AExecute) -> None:
    res = await aexecute(ENSURE_CALL, {"input": {"about": []}})
    assert res.errors


async def test_join_call_mints_a_publishing_token_for_the_room(
    aexecute: AExecute,
) -> None:
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call = data_of(created)["ensureCall"]

    res = await aexecute(JOIN_CALL, {"input": {"call": call["id"]}})
    assert not res.errors, res.errors
    assert res.data is not None

    claims = jwt.decode(
        res.data["joinCall"]["credential"], options={"verify_signature": False}
    )
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


async def test_join_call_twice_gives_two_identities(aexecute: AExecute) -> None:
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]
    first = await aexecute(JOIN_CALL, {"input": {"call": call_id}})
    second = await aexecute(JOIN_CALL, {"input": {"call": call_id}})
    identity = lambda token: jwt.decode(token, options={"verify_signature": False})[  # noqa: E731
        "sub"
    ]
    # A second window joins beside the first instead of kicking it out.
    assert identity(data_of(first)["joinCall"]["credential"]) != identity(
        data_of(second)["joinCall"]["credential"]
    )


async def test_calls_about_a_structure_and_their_liveness(aexecute: AExecute) -> None:
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]

    live = await aexecute(CALLS_ABOUT, {"about": IMAGE, "live": True})
    assert not live.errors, live.errors
    assert live.data is not None
    assert [c["id"] for c in live.data["calls"]] == [call_id]
    assert live.data["calls"][0]["participantCount"] == 0

    nobody = await aexecute(
        CALLS_ABOUT, {"about": {"identifier": "@mikro/image", "object": 999}}
    )
    assert data_of(nobody)["calls"] == []

    down = await aexecute(CALLS_ABOUT, {"about": IMAGE, "live": False})
    assert data_of(down)["calls"] == []


async def test_calls_are_scoped_to_the_organization(
    aexecute: AExecute, authenticated_context: HttpContext
) -> None:
    """A call of another organization does not exist for the caller."""
    from tests.conftest import _make_context

    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]

    from asgiref.sync import sync_to_async

    # The extension re-resolves the organization from the token, so another
    # organization needs its own static token (see settings_test).
    stranger = await sync_to_async(_make_context)(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )

    listed = await aexecute(CALLS_ABOUT, {"about": IMAGE}, context=stranger)
    assert not listed.errors, listed.errors
    assert listed.data is not None
    assert listed.data["calls"] == []

    joined = await aexecute(JOIN_CALL, {"input": {"call": call_id}}, context=stranger)
    assert joined.errors


ADD_TO_CALL = """
mutation ($input: AddToCallInput!) {
  addToCall(input: $input) { id title about { identifier object } }
}
"""

OTHER_IMAGE = {"identifier": "@mikro/image", "object": 43}


def _about(call: dict) -> list[tuple[str, int]]:
    """What the call is about, in the order it reports: oldest first."""
    return [
        (structure["identifier"], structure["object"]) for structure in call["about"]
    ]


async def test_add_to_call_keeps_what_the_call_was_about(aexecute: AExecute) -> None:
    created = await aexecute(
        ENSURE_CALL, {"input": {"about": [IMAGE], "title": "Look at this"}}
    )
    call_id = data_of(created)["ensureCall"]["id"]

    res = await aexecute(
        ADD_TO_CALL, {"input": {"call": call_id, "about": [OTHER_IMAGE]}}
    )
    assert not res.errors, res.errors
    assert res.data is not None
    assert _about(res.data["addToCall"]) == [("@mikro/image", 42), ("@mikro/image", 43)]
    assert res.data["addToCall"]["title"] == "Look at this"

    # Adding what it is already about changes nothing.
    again = await aexecute(
        ADD_TO_CALL, {"input": {"call": call_id, "about": [IMAGE, OTHER_IMAGE]}}
    )
    assert _about(data_of(again)["addToCall"]) == [
        ("@mikro/image", 42),
        ("@mikro/image", 43),
    ]


async def test_adding_an_earlier_topic_again_turns_the_call_back_to_it(
    aexecute: AExecute,
) -> None:
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]
    await aexecute(ADD_TO_CALL, {"input": {"call": call_id, "about": [OTHER_IMAGE]}})

    back = await aexecute(ADD_TO_CALL, {"input": {"call": call_id, "about": [IMAGE]}})
    assert not back.errors, back.errors
    assert back.data is not None
    # Nothing lost, and the image is the current topic again.
    assert _about(back.data["addToCall"]) == [
        ("@mikro/image", 43),
        ("@mikro/image", 42),
    ]


async def test_what_a_call_is_about_comes_in_the_order_it_was_added(
    aexecute: AExecute,
) -> None:
    """The last one is the current topic, whatever was first called about elsewhere."""
    # Image 43 exists as a structure before image 42 does.
    await aexecute(ENSURE_CALL, {"input": {"about": [OTHER_IMAGE]}})
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]

    await aexecute(
        ADD_TO_CALL,
        {
            "input": {
                "call": call_id,
                "about": [{"identifier": "@kraph/entity", "object": 5}, OTHER_IMAGE],
            }
        },
    )
    read = await aexecute(
        "query ($id: ID!) { call(id: $id) { about { identifier object } } }",
        {"id": call_id},
    )
    assert not read.errors, read.errors
    assert read.data is not None
    assert _about(read.data["call"]) == [
        ("@mikro/image", 42),
        ("@kraph/entity", 5),
        ("@mikro/image", 43),
    ]

    listed = await aexecute(
        CALLS_ABOUT.replace("participantCount", "about { identifier object }"),
        {"about": IMAGE, "live": True},
    )
    assert not listed.errors, listed.errors
    assert listed.data is not None
    assert _about(listed.data["calls"][0]) == [
        ("@mikro/image", 42),
        ("@kraph/entity", 5),
        ("@mikro/image", 43),
    ]


async def test_a_call_with_a_new_topic_is_still_the_call_about_its_first(
    aexecute: AExecute,
) -> None:
    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]
    await aexecute(ADD_TO_CALL, {"input": {"call": call_id, "about": [OTHER_IMAGE]}})

    # "Call about this" on either image lands in the room, not beside it.
    first = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    added = await aexecute(ENSURE_CALL, {"input": {"about": [OTHER_IMAGE]}})
    assert data_of(first)["ensureCall"]["id"] == call_id
    assert data_of(added)["ensureCall"]["id"] == call_id

    listed = await aexecute(CALLS_ABOUT, {"about": OTHER_IMAGE, "live": True})
    assert [c["id"] for c in data_of(listed)["calls"]] == [call_id]


async def test_the_call_about_exactly_this_wins_over_one_about_more(
    aexecute: AExecute,
) -> None:
    wide = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE, OTHER_IMAGE]}})
    narrow = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    # No call was about the image alone, but one was about it: reused.
    assert data_of(narrow)["ensureCall"]["id"] == data_of(wide)["ensureCall"]["id"]

    alone = await aexecute(
        ENSURE_CALL,
        {"input": {"about": [{"identifier": "@mikro/image", "object": 44}]}},
    )
    await aexecute(
        ADD_TO_CALL,
        {
            "input": {
                "call": data_of(wide)["ensureCall"]["id"],
                "about": [{"identifier": "@mikro/image", "object": 44}],
            }
        },
    )
    again = await aexecute(
        ENSURE_CALL,
        {"input": {"about": [{"identifier": "@mikro/image", "object": 44}]}},
    )
    assert data_of(again)["ensureCall"]["id"] == data_of(alone)["ensureCall"]["id"]


async def test_add_to_call_needs_something_and_a_call_of_ones_own_organization(
    aexecute: AExecute,
) -> None:
    from asgiref.sync import sync_to_async

    from tests.conftest import _make_context

    created = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = data_of(created)["ensureCall"]["id"]

    nothing = await aexecute(ADD_TO_CALL, {"input": {"call": call_id, "about": []}})
    assert nothing.errors

    stranger = await sync_to_async(_make_context)(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )
    theirs = await aexecute(
        ADD_TO_CALL,
        {"input": {"call": call_id, "about": [OTHER_IMAGE]}},
        context=stranger,
    )
    assert theirs.errors
    assert await Call.objects.filter(id=call_id, about__object=43).acount() == 0
