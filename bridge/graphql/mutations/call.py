"""Finding, starting and joining calls.

A call is a LiveKit room about some structures. ``ensureCall`` hands back the
live call about exactly those structures when there is one, so two people
pressing "Call about this" on the same image land in the same room; otherwise
it starts a new one. ``joinCall`` mints the token that lets the caller publish
and subscribe in that room.
"""

import json
import logging
import secrets

from asgiref.sync import sync_to_async
from django.db.models import Count
from kante.types import Info
from livekit import api as lapi
from django.conf import settings

from bridge import calls, inputs, models, types
from bridge.graphql.mutations.invite import clear_invites_on_join

logger = logging.getLogger(__name__)


def _structures(about: list[inputs.StructureInput]) -> list[models.Structure]:
    """The structure rows for these references, created when new."""
    rows = []
    for reference in about:
        row, _ = models.Structure.objects.get_or_create(identifier=reference.identifier, object=reference.object)
        rows.append(row)
    return rows


def _title(input: inputs.EnsureCallInput) -> str:
    if input.title:
        return input.title
    if len(input.about) == 1:
        return f"Call about {input.about[0].identifier} {input.about[0].object}"
    return f"Call about {len(input.about)} structures"


@sync_to_async
def _find_or_create(info: Info, input: inputs.EnsureCallInput, live: set[str]) -> tuple[models.Call, bool]:
    organization = info.context.request.organization
    structures = _structures(input.about)

    # The newest live call about exactly these structures, if any.
    candidates = models.Call.objects.filter(organization=organization).annotate(n_about=Count("about")).filter(n_about=len(structures))
    for structure in structures:
        candidates = candidates.filter(about=structure)
    for call in candidates.order_by("-created_at"):
        if call.livekit_room_name in live:
            return call, False

    call = models.Call.objects.create(
        title=_title(input),
        organization=organization,
        creator=info.context.request.user,
    )
    call.about.set(structures)
    return call, True


async def ensure_call(info: Info, input: inputs.EnsureCallInput) -> types.Call:
    """The live call about these structures, or a new one."""
    if not input.about:
        raise ValueError("A call needs something to be about")
    live = await calls.live_room_names()
    call, created = await _find_or_create(info, input, live)
    # Idempotent in LiveKit too: a reused call's room already exists.
    await calls.create_room(call.livekit_room_name)
    logger.info("%s call %s (%s)", "Started" if created else "Rejoined", call.id, call.livekit_room_name)
    return call


async def join_call(info: Info, input: inputs.JoinCallInput) -> str:
    """A token to publish and subscribe in the call's room.

    Scoped first: a call of another organization does not exist for this
    caller. The identity carries a nonce so a second window of the same user
    joins beside the first instead of replacing it; the name and metadata
    are what the others see and group by.
    """
    user = info.context.request.user
    call = await models.Call.objects.aget(id=input.call, organization=info.context.request.organization)
    await calls.create_room(call.livekit_room_name)
    # Answered: the invitation stops ringing on the user's other devices too.
    await clear_invites_on_join(info, call)

    return (
        lapi.AccessToken(
            api_key=settings.LIVEKIT["API_KEY"],
            api_secret=settings.LIVEKIT["API_SECRET"],
        )
        .with_identity(f"user-{user.id}-{secrets.token_hex(3)}")
        .with_name(user.username)
        .with_metadata(json.dumps({"user": user.id, "sub": user.sub}))
        .with_grants(
            lapi.VideoGrants(
                room_join=True,
                room=call.livekit_room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )
