"""What LiveKit knows about a call: whether its room is up, and who is in it.

A call row says what a call is about; LiveKit says whether it is live. Every
helper here opens its own API client and closes it again, so a resolver that
runs in a worker thread (a filter) can drive it through ``async_to_sync``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from livekit.api import TwirpError
from livekit.protocol.room import CreateRoomRequest, ListParticipantsRequest, ListRoomsRequest

from bridge import api

logger = logging.getLogger(__name__)

# How long LiveKit keeps the room after the last participant leaves, in
# seconds. Long enough that a reconnect finds the room, short enough that a
# call nobody is in stops counting as live.
EMPTY_TIMEOUT = 120


@dataclass(frozen=True)
class Participant:
    """One participant of a live room, as LiveKit reports them."""

    identity: str
    name: str
    joined_at: int
    metadata: str


async def create_room(name: str) -> None:
    """Make sure the LiveKit room ``name`` exists (idempotent)."""
    client = api.get_api()
    try:
        await client.room.create_room(CreateRoomRequest(name=name, empty_timeout=EMPTY_TIMEOUT))
    finally:
        await client.aclose()


async def live_room_names() -> set[str]:
    """The names of every LiveKit room that currently exists."""
    client = api.get_api()
    try:
        response = await client.room.list_rooms(ListRoomsRequest())
        return {room.name for room in response.rooms}
    finally:
        await client.aclose()


async def participants(room_name: str) -> list[Participant]:
    """Who is in ``room_name`` now; nobody when the room does not exist."""
    client = api.get_api()
    try:
        response = await client.room.list_participants(ListParticipantsRequest(room=room_name))
    except TwirpError as error:
        # LiveKit answers "not_found" for a room that timed out; that is an
        # empty call, not a failure.
        logger.debug("No participants for %s: %s", room_name, error)
        return []
    finally:
        await client.aclose()
    return [
        Participant(
            identity=participant.identity,
            name=participant.name,
            joined_at=participant.joined_at,
            metadata=participant.metadata,
        )
        for participant in response.participants
    ]
