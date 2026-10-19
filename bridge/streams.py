"""What LiveKit knows about an agent's streams: which of its tracks are being published.

A stream row says what an agent declared; LiveKit says whether it is live. A stream is live
while the agent's publisher (``agent-<id>``) is in the agent's room with a track named after
the stream's key. Like :mod:`bridge.calls`, every helper opens its own API client and closes
it again.
"""

from __future__ import annotations

import asyncio
import logging

from livekit.api import TwirpError
from livekit.protocol.room import ListParticipantsRequest
from strawberry.dataloader import DataLoader

from bridge import api, calls

logger = logging.getLogger(__name__)


async def published_tracks(room_name: str, publisher: str) -> set[str]:
    """The names of the tracks ``publisher`` publishes in ``room_name`` now; none when the room is gone."""
    client = api.get_api()
    try:
        response = await client.room.list_participants(ListParticipantsRequest(room=room_name))
    except TwirpError as error:
        # LiveKit answers "not_found" for a room nobody joined or that timed out: an agent
        # that is not streaming, not a failure.
        logger.debug("No participants for %s: %s", room_name, error)
        return set()
    finally:
        await client.aclose()
    return {track.name for participant in response.participants if participant.identity == publisher for track in participant.tracks}


def agent_ids(room_names: set[str]) -> list[int]:
    """The agents these LiveKit rooms belong to (an agent's room is ``agent-<id>``)."""
    return [int(name[6:]) for name in room_names if name.startswith("agent-") and name[6:].isdigit()]


async def live_tracks() -> dict[int, set[str]]:
    """Every agent whose room is up, with the tracks its publisher publishes there now."""
    ids = agent_ids(await calls.live_room_names())
    tracks = await asyncio.gather(*(published_tracks(f"agent-{id}", f"agent-{id}") for id in ids))
    return dict(zip(ids, tracks))


async def _load(keys: list[tuple[str, str]]) -> list[set[str]]:
    # Without a cache, every stream of one agent brings its key into the batch: ask once each.
    unique = list(dict.fromkeys(keys))
    answers = dict(zip(unique, await asyncio.gather(*(published_tracks(room_name, publisher) for room_name, publisher in unique))))
    return [answers[key] for key in keys]


def tracks_loader(context) -> DataLoader[tuple[str, str], set[str]]:
    """The context's loader of published tracks, keyed by ``(room, publisher)``.

    Kept on the context, so the streams of one answer ask LiveKit once per agent, not once
    per stream. It batches and never caches: a websocket's context outlives many answers,
    and each of them is LiveKit's answer of the moment.
    """
    loader = getattr(context, "_lovekit_tracks", None)
    if loader is None:
        loader = DataLoader(load_fn=_load, cache=False)
        setattr(context, "_lovekit_tracks", loader)
    return loader
