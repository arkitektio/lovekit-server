"""The one way this service mints a LiveKit access token.

LiveKit keeps one connection per identity in a room: a second connection with
an identity already present replaces the first. So every token gets an
identity of its own — ``<kind>-<id>-<nonce>`` — and a second window, viewer
or streamer joins beside the first instead of kicking it out. The prefix
(``user``, ``streamer``) is what the apps tell participants apart by; the
name is what the others see, and the metadata says who is behind it.
"""

import json
import secrets

from django.conf import settings
from livekit import api as lapi


def display_name(user) -> str:
    """The preferred username (authentikate keeps it on ``first_name``), not the iss_sub artifact."""
    return user.first_name or user.username


def participant_token(
    room: str,
    *,
    kind: str,
    id: int,
    user,
    can_publish: bool,
    can_publish_data: bool = False,
    metadata: dict | None = None,
) -> str:
    """A token to join ``room`` as a fresh ``<kind>-<id>-<nonce>`` participant."""
    return (
        lapi.AccessToken(
            api_key=settings.LIVEKIT["API_KEY"],
            api_secret=settings.LIVEKIT["API_SECRET"],
        )
        .with_identity(f"{kind}-{id}-{secrets.token_hex(3)}")
        .with_name(display_name(user))
        .with_metadata(json.dumps({"user": user.id, "sub": user.sub, **(metadata or {})}))
        .with_grants(
            lapi.VideoGrants(
                room_join=True,
                room=room,
                can_publish=can_publish,
                can_subscribe=True,
                can_publish_data=can_publish_data,
            )
        )
        .to_jwt()
    )
