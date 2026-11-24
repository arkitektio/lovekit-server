"""Watching: everyone of the agent's organization may, nobody else, and a watcher never publishes."""

import pytest
from django.conf import settings
from kante.context import HttpContext
from livekit.api import TokenVerifier
from livekit.api.access_token import Claims

from tests.support import AExecute, data_of

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]

DECLARE = """
mutation ($input: DeclareStreamsInput!) {
  declareStreams(input: $input) { id agent { id roomName } }
}
"""

WATCH_STREAM = """
mutation ($input: WatchStreamInput!) { watchStream(input: $input) { transport credential } }
"""

WATCH_AGENT = """
mutation ($input: WatchAgentInput!) { watchAgent(input: $input) { transport credential } }
"""

STREAM = "query ($id: ID!) { stream(id: $id) { id } }"
STREAMS = "{ streams { id } agents { id } }"


def _claims(token: str) -> Claims:
    return TokenVerifier(
        settings.LIVEKIT["API_KEY"], settings.LIVEKIT["API_SECRET"]
    ).verify(token)


async def _stream(aexecute: AExecute) -> dict:
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": "camera"}]}})
    assert not res.errors, res.errors
    assert res.data is not None
    return res.data["declareStreams"][0]


async def test_a_member_watches_a_stream_without_publishing(
    aexecute: AExecute, other_user_context: HttpContext
) -> None:
    stream = await _stream(aexecute)
    res = await aexecute(
        WATCH_STREAM, {"input": {"stream": stream["id"]}}, context=other_user_context
    )
    assert not res.errors, res.errors
    assert res.data is not None

    claims = _claims(res.data["watchStream"]["credential"])
    assert claims.video.room == stream["agent"]["roomName"]
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish is False
    # A member gets data packets for RPC: it times latency pings to the agent (`lovekit.ping`).
    assert claims.video is not None
    assert claims.video.can_publish_data is True
    # A watcher's identity is its own, so two windows watch side by side.
    assert claims.identity.startswith("user-")
    again = await aexecute(
        WATCH_STREAM, {"input": {"stream": stream["id"]}}, context=other_user_context
    )
    assert (
        _claims(data_of(again)["watchStream"]["credential"]).identity != claims.identity
    )


async def test_a_member_watches_a_whole_agent(
    aexecute: AExecute, other_user_context: HttpContext
) -> None:
    stream = await _stream(aexecute)
    res = await aexecute(
        WATCH_AGENT,
        {"input": {"agent": stream["agent"]["id"]}},
        context=other_user_context,
    )
    assert not res.errors, res.errors
    assert res.data is not None
    assert (
        _claims(res.data["watchAgent"]["credential"]).video.room
        == stream["agent"]["roomName"]
    )


async def test_an_agent_is_found_by_its_app(aexecute: AExecute) -> None:
    stream = await _stream(aexecute)
    # The static test token's client is "static" (authentikate's StaticToken default).
    res = await aexecute('{ agents(filters: { search: "stat" }) { id name } }')
    assert not res.errors, res.errors
    assert res.data is not None
    assert res.data["agents"] == [{"id": stream["agent"]["id"], "name": "static"}]
    res = await aexecute(
        '{ agents(filters: { clientId: "static", userSub: "1" }) { id } streams(filters: { clientId: "static", userSub: "1" }) { id } }'
    )
    assert res.data == {
        "agents": [{"id": stream["agent"]["id"]}],
        "streams": [{"id": stream["id"]}],
    }


async def test_another_organization_sees_no_stream(
    aexecute: AExecute, stranger_context: HttpContext
) -> None:
    stream = await _stream(aexecute)

    for document, variables in [
        (WATCH_STREAM, {"input": {"stream": stream["id"]}}),
        (WATCH_AGENT, {"input": {"agent": stream["agent"]["id"]}}),
        (STREAM, {"id": stream["id"]}),
    ]:
        res = await aexecute(document, variables, context=stranger_context)
        assert res.errors, document

    res = await aexecute(STREAMS, context=stranger_context)
    assert not res.errors, res.errors
    assert res.data is not None
    assert res.data == {"streams": [], "agents": []}
