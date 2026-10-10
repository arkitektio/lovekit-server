"""A call starting is announced to its organization's open apps, once."""

import asyncio
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer

from bridge.channel_signals import CallSignal
from bridge.channels import call_channel
from bridge.graphql.mutations.call import call_group
from bridge.graphql.subscriptions import call as subscription
from bridge.models import Call

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.docker]

ENSURE_CALL = """
mutation ($input: EnsureCallInput!) { ensureCall(input: $input) { id } }
"""

IMAGE = {"identifier": "@mikro/image", "object": 42}


async def _listen(organization) -> tuple[object, str]:
    """A channel in the organization's group, as a subscriber's consumer holds one."""
    layer = get_channel_layer()
    channel = await layer.new_channel()
    await layer.group_add(call_group(organization), channel)
    return layer, channel


async def _next(layer, channel) -> CallSignal | None:
    """The next announcement on ``channel``, or None when nothing was sent."""
    try:
        message = await asyncio.wait_for(layer.receive(channel), timeout=0.5)
    except asyncio.TimeoutError:
        return None
    assert message["type"] == call_channel.message_type
    return CallSignal.model_validate(message["message"])


async def _events(context, signals: list[CallSignal]) -> list[tuple[str, str]]:
    """What the ``calls`` subscription yields to ``context`` for these signals, as (kind, call id)."""

    async def listen(info, groups):
        assert groups == [call_group(context.request.organization)]
        for signal in signals:
            yield signal

    info = SimpleNamespace(context=context)
    original = call_channel.listen
    call_channel.listen = listen
    try:
        return [
            ("create", str(event.create.id)) if event.create else ("update", str(event.update.id))
            async for event in subscription.calls(None, info)
        ]
    finally:
        call_channel.listen = original


async def _heard(context, signals: list[CallSignal]) -> list[str]:
    """The calls the subscription announces to ``context`` as started."""
    return [call_id for kind, call_id in await _events(context, signals) if kind == "create"]


async def test_a_new_call_is_announced_to_its_organization(aexecute, authenticated_context):
    layer, channel = await _listen(authenticated_context.request.organization)

    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not res.errors, res.errors

    signal = await _next(layer, channel)
    assert signal is not None
    assert str(signal.create) == res.data["ensureCall"]["id"]


async def test_a_reused_call_is_not_announced_again(aexecute, authenticated_context):
    layer, channel = await _listen(authenticated_context.request.organization)

    await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert await _next(layer, channel) is not None

    # The room is still up, so this lands in the same call: no second ring.
    again = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not again.errors, again.errors
    assert await _next(layer, channel) is None


async def test_another_organization_hears_nothing(aexecute):
    from tests.conftest import _make_context

    stranger = await sync_to_async(_make_context)(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )
    layer, channel = await _listen(stranger.request.organization)

    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    assert not res.errors, res.errors
    assert await _next(layer, channel) is None


async def test_the_subscription_tells_the_others_and_not_the_starter(aexecute, authenticated_context, other_user_context):
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = res.data["ensureCall"]["id"]
    signals = [CallSignal(create=int(call_id))]

    assert await _heard(other_user_context, signals) == [call_id]
    # Whoever started it is on their way in already.
    assert await _heard(authenticated_context, signals) == []


async def test_the_subscription_drops_a_call_of_another_organization(aexecute, other_user_context):
    """Scoped on the way out as well: a stray signal is not a way across tenants."""
    from tests.conftest import _make_context

    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = int(res.data["ensureCall"]["id"])
    assert await Call.objects.filter(id=call_id).aexists()

    stranger = await sync_to_async(_make_context)(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )
    assert await _heard(stranger, [CallSignal(create=call_id), CallSignal(create=999_999)]) == []


async def test_an_open_app_hears_the_call_over_its_websocket(aexecute, other_user_context):
    """The whole way: a subscriber's socket, the group it joins, the call as it yields."""
    from kante.testing import GraphQLWebSocketTestClient

    from lovekit_server.asgi import application

    async with GraphQLWebSocketTestClient(application, connection_params={"token": "othertest"}) as client:
        heard = client.subscribe("subscription { calls { create { id title } } }", timeout=3, max_messages=1)
        listening = asyncio.ensure_future(anext(heard))
        # Let the subscription join its group before the call starts.
        await asyncio.sleep(0.3)

        res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE], "title": "Look at this"}})
        assert not res.errors, res.errors

        message = await listening
        assert message["payload"]["data"]["calls"]["create"] == {
            "id": res.data["ensureCall"]["id"],
            "title": "Look at this",
        }


ADD_TO_CALL = """
mutation ($input: AddToCallInput!) { addToCall(input: $input) { id } }
"""

OTHER_IMAGE = {"identifier": "@mikro/image", "object": 43}


async def test_a_new_topic_is_told_to_the_organization_once(aexecute, authenticated_context):
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = res.data["ensureCall"]["id"]
    layer, channel = await _listen(authenticated_context.request.organization)

    added = await aexecute(ADD_TO_CALL, {"input": {"call": call_id, "about": [OTHER_IMAGE]}})
    assert not added.errors, added.errors
    signal = await _next(layer, channel)
    assert signal is not None
    assert (signal.create, str(signal.update)) == (None, call_id)

    # Already about it: nothing changed, nothing to tell.
    await aexecute(ADD_TO_CALL, {"input": {"call": call_id, "about": [OTHER_IMAGE]}})
    assert await _next(layer, channel) is None


async def test_a_new_topic_reaches_everyone_the_starter_included(aexecute, authenticated_context, other_user_context):
    res = await aexecute(ENSURE_CALL, {"input": {"about": [IMAGE]}})
    call_id = res.data["ensureCall"]["id"]
    signals = [CallSignal(update=int(call_id))]

    assert await _events(authenticated_context, signals) == [("update", call_id)]
    assert await _events(other_user_context, signals) == [("update", call_id)]
