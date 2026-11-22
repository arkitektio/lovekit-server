"""Invitations: what rings an invitee's apps, and what stops it."""

import pytest
from kante.context import HttpContext

from bridge.models import CallInvite
from tests.support import AExecute, data_of

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]

ENSURE_CALL = """
mutation ($input: EnsureCallInput!) { ensureCall(input: $input) { id } }
"""
INVITE = """
mutation ($input: InviteToCallInput!) { inviteToCall(input: $input) { id } }
"""
MY_INVITES = """
query { myCallInvites { id call { id title } inviter { sub } } }
"""
JOIN_CALL = """
mutation ($input: JoinCallInput!) { joinCall(input: $input) { transport credential } }
"""
DISMISS = """
mutation ($input: DismissCallInviteInput!) { dismissCallInvite(input: $input) }
"""

IMAGE = {"identifier": "@mikro/image", "object": 42}


async def _call(aexecute: AExecute) -> str:
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not res.errors, res.errors
    assert res.data is not None
    return res.data["ensureCall"]["id"]


async def test_invite_reaches_the_invitee_and_nobody_else(
    aexecute: AExecute, other_user_context: HttpContext
) -> None:
    call_id = await _call(aexecute)
    # The invitee is addressed by their lok id, the `sub` of their token.
    res = await aexecute(INVITE, {"input": {"call": call_id, "users": ["9"]}})
    assert not res.errors, res.errors

    theirs = await aexecute(MY_INVITES, context=other_user_context)
    assert not theirs.errors, theirs.errors
    assert theirs.data is not None
    assert [i["call"]["id"] for i in theirs.data["myCallInvites"]] == [call_id]
    assert theirs.data["myCallInvites"][0]["inviter"]["sub"] == "1"

    mine = await aexecute(MY_INVITES)
    assert data_of(mine)["myCallInvites"] == []


async def test_inviting_twice_rings_once(
    aexecute: AExecute, other_user_context: HttpContext
) -> None:
    call_id = await _call(aexecute)
    await aexecute(INVITE, {"input": {"call": call_id, "users": ["9"]}})
    await aexecute(INVITE, {"input": {"call": call_id, "users": ["9"]}})
    assert await CallInvite.objects.filter(call_id=call_id).acount() == 1


async def test_unknown_people_and_oneself_are_skipped(aexecute: AExecute) -> None:
    call_id = await _call(aexecute)
    res = await aexecute(
        INVITE, {"input": {"call": call_id, "users": ["1", "nobody-here"]}}
    )
    assert not res.errors, res.errors
    assert await CallInvite.objects.filter(call_id=call_id).acount() == 0


async def test_joining_from_any_device_answers_the_invite(
    aexecute: AExecute, other_user_context: HttpContext
) -> None:
    call_id = await _call(aexecute)
    await aexecute(INVITE, {"input": {"call": call_id, "users": ["9"]}})

    joined = await aexecute(
        JOIN_CALL, {"input": {"call": call_id}}, context=other_user_context
    )
    assert not joined.errors, joined.errors

    theirs = await aexecute(MY_INVITES, context=other_user_context)
    assert data_of(theirs)["myCallInvites"] == []


async def test_dismissing_puts_the_invite_away(
    aexecute: AExecute, other_user_context: HttpContext
) -> None:
    call_id = await _call(aexecute)
    await aexecute(INVITE, {"input": {"call": call_id, "users": ["9"]}})
    theirs = await aexecute(MY_INVITES, context=other_user_context)
    invite_id = data_of(theirs)["myCallInvites"][0]["id"]

    # Only the invitee can dismiss it.
    not_mine = await aexecute(DISMISS, {"input": {"id": invite_id}})
    assert not not_mine.errors
    still = await aexecute(MY_INVITES, context=other_user_context)
    assert len(data_of(still)["myCallInvites"]) == 1

    gone = await aexecute(
        DISMISS, {"input": {"id": invite_id}}, context=other_user_context
    )
    assert not gone.errors, gone.errors
    after = await aexecute(MY_INVITES, context=other_user_context)
    assert data_of(after)["myCallInvites"] == []
