"""Watching: everyone of the agent's organization may, nobody else, and a watcher never publishes."""

import pytest
from django.conf import settings
from livekit.api import TokenVerifier

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.docker]

DECLARE = """
mutation ($input: DeclareStreamsInput!) {
  declareStreams(input: $input) { id agent { id roomName } }
}
"""

WATCH_STREAM = """
mutation ($input: WatchStreamInput!) { watchStream(input: $input) }
"""

WATCH_AGENT = """
mutation ($input: WatchAgentInput!) { watchAgent(input: $input) }
"""

STREAM = "query ($id: ID!) { stream(id: $id) { id } }"
STREAMS = "{ streams { id } agents { id } }"


def _claims(token: str):
    return TokenVerifier(settings.LIVEKIT["API_KEY"], settings.LIVEKIT["API_SECRET"]).verify(token)


async def _stream(aexecute):
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": "camera"}]}})
    assert not res.errors, res.errors
    return res.data["declareStreams"][0]


async def test_a_member_watches_a_stream_without_publishing(aexecute, other_user_context):
    stream = await _stream(aexecute)
    res = await aexecute(WATCH_STREAM, {"input": {"stream": stream["id"]}}, context=other_user_context)
    assert not res.errors, res.errors

    claims = _claims(res.data["watchStream"])
    assert claims.video.room == stream["agent"]["roomName"]
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish is False
    # A watcher's identity is its own, so two windows watch side by side.
    assert claims.identity.startswith("user-")
    again = await aexecute(WATCH_STREAM, {"input": {"stream": stream["id"]}}, context=other_user_context)
    assert _claims(again.data["watchStream"]).identity != claims.identity


async def test_a_member_watches_a_whole_agent(aexecute, other_user_context):
    stream = await _stream(aexecute)
    res = await aexecute(WATCH_AGENT, {"input": {"agent": stream["agent"]["id"]}}, context=other_user_context)
    assert not res.errors, res.errors
    assert _claims(res.data["watchAgent"]).video.room == stream["agent"]["roomName"]


async def test_an_agent_is_found_by_its_app(aexecute):
    stream = await _stream(aexecute)
    # The static test token's client is "static" (authentikate's StaticToken default).
    res = await aexecute('{ agents(filters: { search: "stat" }) { id name } }')
    assert not res.errors, res.errors
    assert res.data["agents"] == [{"id": stream["agent"]["id"], "name": "static"}]
    res = await aexecute('{ agents(filters: { clientId: "static", userSub: "1" }) { id } streams(filters: { clientId: "static", userSub: "1" }) { id } }')
    assert res.data == {"agents": [{"id": stream["agent"]["id"]}], "streams": [{"id": stream["id"]}]}


async def test_another_organization_sees_no_stream(aexecute, stranger_context):
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
    assert res.data == {"streams": [], "agents": []}
