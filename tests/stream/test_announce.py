"""An agent's declaration is told to its organization's open apps: what changed, and only that."""

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from channels.layers import BaseChannelLayer, get_channel_layer
from kante.context import HttpContext, Organization

from bridge.channel_signals import StreamSignal
from bridge.channels import stream_channel
from bridge.graphql.mutations.stream import stream_group
from bridge.graphql.subscriptions import stream as subscription
from tests.support import AExecute

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]

DECLARE = """
mutation ($input: DeclareStreamsInput!) { declareStreams(input: $input) { id key } }
"""


async def _declare(aexecute: AExecute, streams: list[dict[str, str]]) -> dict[str, str]:
    res = await aexecute(DECLARE, {"input": {"streams": streams}})
    assert not res.errors, res.errors
    assert res.data is not None
    return {stream["key"]: stream["id"] for stream in res.data["declareStreams"]}


async def _listen(organization: Organization) -> tuple[BaseChannelLayer, str]:
    """A channel in the organization's group, as a subscriber's consumer holds one."""
    layer = get_channel_layer()
    assert layer is not None
    channel = await layer.new_channel()
    await layer.group_add(stream_group(organization), channel)
    return layer, channel


async def _heard(layer: BaseChannelLayer, channel: str) -> list[StreamSignal]:
    """Everything announced on ``channel`` until it falls quiet."""
    heard = []
    while True:
        try:
            message = await asyncio.wait_for(layer.receive(channel), timeout=0.5)
        except TimeoutError:
            return heard
        assert message["type"] == stream_channel.message_type
        heard.append(StreamSignal.model_validate(message["message"]))


async def _events(
    context: HttpContext, signals: list[StreamSignal]
) -> list[tuple[str, str]]:
    """What the ``streams`` subscription yields to ``context`` for these signals, as (kind, stream id)."""

    async def listen(info: object, groups: list[str]) -> AsyncIterator[StreamSignal]:
        assert groups == [stream_group(context.request.organization)]
        for signal in signals:
            yield signal

    info = SimpleNamespace(context=context)
    original = stream_channel.listen
    stream_channel.listen = listen
    try:
        events = []
        async for event in subscription.streams(None, info):
            if event.delete is not None:
                events.append(("delete", str(event.delete)))
            elif event.create is not None:
                events.append(("create", str(event.create.id)))
            else:
                events.append(("update", str(event.update.id)))
        return events
    finally:
        stream_channel.listen = original


async def test_a_declaration_is_announced_as_it_changes(
    aexecute: AExecute, authenticated_context: HttpContext
) -> None:
    layer, channel = await _listen(authenticated_context.request.organization)

    ids = await _declare(aexecute, [{"key": "camera"}, {"key": "overview"}])
    assert await _heard(layer, channel) == [
        StreamSignal(create=int(ids["camera"])),
        StreamSignal(create=int(ids["overview"])),
    ]

    # A restart that declares the same: nothing to tell.
    await _declare(aexecute, [{"key": "camera"}, {"key": "overview"}])
    assert await _heard(layer, channel) == []

    await _declare(aexecute, [{"key": "camera", "title": "Main camera"}])
    assert await _heard(layer, channel) == [
        StreamSignal(update=int(ids["camera"])),
        StreamSignal(delete=int(ids["overview"])),
    ]


async def test_the_subscription_yields_only_its_organizations_streams(
    aexecute: AExecute, authenticated_context: HttpContext
) -> None:
    from tests.conftest import _make_context

    ids = await _declare(aexecute, [{"key": "camera"}])
    camera = int(ids["camera"])

    signals = [
        StreamSignal(create=camera),
        StreamSignal(update=camera),
        StreamSignal(create=999_999),
        StreamSignal(delete=camera),
    ]
    assert await _events(authenticated_context, signals) == [
        ("create", str(camera)),
        ("update", str(camera)),
        ("delete", str(camera)),
    ]

    stranger = await sync_to_async(_make_context)(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )
    # Another organization's subscriber is never in this group; were it handed the signal
    # anyway, the stream is not found for it.
    assert [kind for kind, _ in await _events(stranger, signals[:2])] == []


async def test_an_open_app_hears_a_new_stream_over_its_websocket(
    aexecute: AExecute,
) -> None:
    """The whole way: a subscriber's socket, the group it joins, the stream as it yields."""
    from kante.testing import GraphQLWebSocketTestClient

    from lovekit_server.asgi import application

    async with GraphQLWebSocketTestClient(
        application, connection_params={"token": "othertest"}
    ) as client:
        heard = client.subscribe(
            "subscription { streams { create { key title } } }",
            timeout=3,
            max_messages=1,
        )
        listening = asyncio.ensure_future(anext(heard))
        # Let the subscription join its group before the agent declares.
        await asyncio.sleep(0.3)

        await _declare(aexecute, [{"key": "camera", "title": "Main camera"}])

        message = await listening
        assert message["payload"]["data"]["streams"]["create"] == {
            "key": "camera",
            "title": "Main camera",
        }
