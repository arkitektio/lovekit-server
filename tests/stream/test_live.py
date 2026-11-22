"""Whether a stream is live is LiveKit's answer: its agent publishes a track named by the stream's key.

These connect to the real LiveKit server of the test stack with the credential ``publisherConnection``
mints, publish real tracks, and read ``live`` back through the schema.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import pytest
from django.conf import settings
from kante.context import HttpContext
from livekit import rtc
from livekit.api import LiveKitAPI, TokenVerifier
from livekit.protocol.room import ListParticipantsRequest

from tests.support import AExecute, data_of

_T = TypeVar("_T")

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]

URL = settings.LIVEKIT["API_URL"].replace("http", "ws", 1)

DECLARE = """
mutation ($input: DeclareStreamsInput!) {
  declareStreams(input: $input) { id key agent { id roomName } }
}
"""

PUBLISH_TOKEN = "mutation { publisherConnection { transport credential } }"

LIVE = """
query ($id: ID!) { stream(id: $id) { live } }
"""

STREAMS = """
query ($live: Boolean) { streams(filters: { live: $live }) { key live } }
"""

AGENT = """
query ($id: ID!) { agent(id: $id) { live streams { key live } } }
"""


async def _declare(
    aexecute: AExecute, keys: list[str], context: HttpContext | None = None
) -> list[dict]:
    res = await aexecute(
        DECLARE, {"input": {"streams": [{"key": key} for key in keys]}}, context=context
    )
    assert not res.errors, res.errors
    assert res.data is not None
    return res.data["declareStreams"]


async def _token(aexecute: AExecute, context: HttpContext | None = None) -> str:
    res = await aexecute(PUBLISH_TOKEN, context=context)
    assert not res.errors, res.errors
    assert res.data is not None
    assert res.data["publisherConnection"]["transport"] == "LIVEKIT"
    return res.data["publisherConnection"]["credential"]


async def _publish(token: str, *names: str) -> tuple[rtc.Room, list[str]]:
    """Connect as the agent and publish one small video track per name."""
    room = rtc.Room()
    reasons: list[str] = []
    room.on(
        "disconnected", lambda reason: reasons.append(rtc.DisconnectReason.Name(reason))
    )
    await asyncio.wait_for(room.connect(URL, token), 20)
    for name in names:
        source = rtc.VideoSource(16, 16)
        track = rtc.LocalVideoTrack.create_video_track(name, source)
        await asyncio.wait_for(
            room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
            ),
            20,
        )
        source.capture_frame(
            rtc.VideoFrame(16, 16, rtc.VideoBufferType.RGBA, bytes(16 * 16 * 4))
        )
    return room, reasons


async def _eventually(
    read: Callable[[], Awaitable[_T]], expected: _T, timeout: float = 10.0
) -> _T:
    """``read()`` once it returns ``expected``: LiveKit lists a track a moment after it is published."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        value = await read()
        if value == expected or asyncio.get_running_loop().time() > deadline:
            return value
        await asyncio.sleep(0.2)


async def test_the_publish_token_is_the_agents_one_identity(aexecute: AExecute) -> None:
    [stream] = await _declare(aexecute, ["camera"])
    token = await _token(aexecute)

    claims = TokenVerifier(
        settings.LIVEKIT["API_KEY"], settings.LIVEKIT["API_SECRET"]
    ).verify(token)
    assert claims.identity == f"agent-{stream['agent']['id']}"
    assert claims.video.room == stream["agent"]["roomName"]
    assert claims.video.can_publish is True
    # Every token of the agent is the same participant: a restart replaces, never duplicates.
    assert (
        TokenVerifier(settings.LIVEKIT["API_KEY"], settings.LIVEKIT["API_SECRET"])
        .verify(await _token(aexecute))
        .identity
        == claims.identity
    )


async def test_there_is_no_publish_token_before_a_declaration(
    aexecute: AExecute,
) -> None:
    res = await aexecute(PUBLISH_TOKEN)
    assert res.errors and "declareStreams" in res.errors[0].message


async def test_a_stream_is_live_while_its_track_is_published(
    aexecute: AExecute,
) -> None:
    camera, overview = await _declare(aexecute, ["camera", "overview"])

    async def live(stream: dict) -> bool:
        res = await aexecute(LIVE, {"id": stream["id"]})
        assert not res.errors, res.errors
        assert res.data is not None
        return res.data["stream"]["live"]

    assert await live(camera) is False

    room, _ = await _publish(await _token(aexecute), "camera")
    try:
        assert await _eventually(lambda: live(camera), True) is True
        # Only the track named by its key makes a stream live.
        assert await live(overview) is False

        agent = await aexecute(AGENT, {"id": camera["agent"]["id"]})
        assert data_of(agent)["agent"]["live"] is True
        assert data_of(agent)["agent"]["streams"] == [
            {"key": "camera", "live": True},
            {"key": "overview", "live": False},
        ]

        res = await aexecute(STREAMS, {"live": True})
        assert data_of(res)["streams"] == [{"key": "camera", "live": True}]
        res = await aexecute(STREAMS, {"live": False})
        assert data_of(res)["streams"] == [{"key": "overview", "live": False}]
    finally:
        await room.disconnect()

    assert await _eventually(lambda: live(camera), False) is False


async def test_a_data_stream_is_live_while_its_data_track_is_published(
    aexecute: AExecute,
) -> None:
    spectrum = {
        "key": "spectrum",
        "kind": "DATA",
        "format": {
            "dtype": "uint8",
            "shape": [16],
            "axes": [{"name": "bin", "type": "INDEX"}],
        },
    }
    res = await aexecute(DECLARE, {"input": {"streams": [spectrum]}})
    assert not res.errors, res.errors
    assert res.data is not None
    [stream] = res.data["declareStreams"]

    async def live() -> bool:
        return data_of(await aexecute(LIVE, {"id": stream["id"]}))["stream"]["live"]

    room = rtc.Room()
    await asyncio.wait_for(room.connect(URL, await _token(aexecute)), 20)
    try:
        track = await room.local_participant.publish_data_track(
            name="spectrum"
        )  # published while it is held
        assert track.is_published()
        assert await _eventually(live, True) is True
    finally:
        await room.disconnect()


async def test_a_restarted_agent_replaces_its_old_connection(
    aexecute: AExecute, livekit_client: LiveKitAPI
) -> None:
    [stream] = await _declare(aexecute, ["camera"])
    old, old_reasons = await _publish(await _token(aexecute), "camera")
    new, _ = await _publish(await _token(aexecute), "camera")
    try:
        room = stream["agent"]["roomName"]

        async def participants() -> list[tuple[str, list[str]]]:
            response = await livekit_client.room.list_participants(
                ListParticipantsRequest(room=room)
            )
            return [
                (p.identity, [t.name for t in p.tracks]) for p in response.participants
            ]

        # One participant, publishing one camera: the new process's.
        identity = f"agent-{stream['agent']['id']}"
        assert await _eventually(participants, [(identity, ["camera"])]) == [
            (identity, ["camera"])
        ]
        # The old process is told why it was let go, so it can stop instead of fighting back.
        assert await _eventually(
            lambda: asyncio.sleep(0, old_reasons), ["DUPLICATE_IDENTITY"]
        ) == ["DUPLICATE_IDENTITY"]
    finally:
        await new.disconnect()
        await old.disconnect()
