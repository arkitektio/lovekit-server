"""Finding, starting and joining calls.

A call is a LiveKit room about some structures. ``ensureCall`` hands back the
live call about those structures when there is one, so two people pressing
"Call about this" on the same image land in the same room; otherwise it
starts a new one, and tells the organization's open apps through the
``calls`` subscription. ``addToCall`` turns a call to something more,
keeping what it was about before (the last one is its current topic). ``joinCall`` mints the token that
lets the caller publish and subscribe in that room.
"""

import json
import logging
import secrets

from asgiref.sync import sync_to_async
from kante.types import Info
from livekit import api as lapi
from django.conf import settings

from bridge import calls, inputs, models, types
from bridge.channel_signals import CallSignal
from bridge.channels import call_channel
from bridge.graphql.mutations.invite import clear_invites_on_join

logger = logging.getLogger(__name__)


def call_group(organization) -> str:
    """The channel group an organization's apps listen on. One definition, both sides.

    Spelled by hand for the reason ``invite_group`` is: ``org_group`` joins
    its parts with colons, which a channel-layer group name may not hold.
    """
    organization_id = getattr(organization, "id", organization)
    return f"calls.org{organization_id}"


def _structures(about: list[inputs.StructureInput]) -> list[models.Structure]:
    """The structure rows for these references, created when new."""
    rows = []
    for reference in about:
        row, _ = models.Structure.objects.get_or_create(identifier=reference.identifier, object=reference.object)
        rows.append(row)
    return rows


def _append_about(call: models.Call, structures: list[models.Structure]) -> None:
    """Add these to what the call is about, one link row each, in this order.

    One at a time: ``add`` with several writes its rows in no particular
    order, and the order of the rows is the order of the topics.
    """
    for structure in structures:
        call.about.add(structure)


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

    # The newest live call about exactly these structures, if any; failing
    # that, one that is about them among other things. A call that took on a
    # second topic (``addToCall``) is still the call about its first.
    candidates = models.Call.objects.filter(organization=organization, id__in=calls.call_ids(live))
    for structure in structures:
        candidates = candidates.filter(about=structure)
    about_these = list(candidates.order_by("-created_at"))
    exactly = [call for call in about_these if call.about.count() == len(structures)]
    if about_these:
        return (exactly or about_these)[0], False

    call = models.Call.objects.create(
        title=_title(input),
        organization=organization,
        creator=info.context.request.user,
    )
    _append_about(call, structures)
    return call, True


async def ensure_call(info: Info, input: inputs.EnsureCallInput) -> types.Call:
    """The live call about these structures, or a new one."""
    if not input.about:
        raise ValueError("A call needs something to be about")
    live = await calls.live_room_names()
    call, created = await _find_or_create(info, input, live)
    # Idempotent in LiveKit too: a reused call's room already exists.
    await calls.create_room(call.livekit_room_name)
    if created:
        # After the room is up, so whoever hears of the call finds it live. A
        # reused call was announced when it started and is not announced again.
        await call_channel.abroadcast(CallSignal(create=call.id), [call_group(call.organization_id)])
    logger.info("%s call %s (%s)", "Started" if created else "Rejoined", call.id, call.livekit_room_name)
    return call


@sync_to_async
def _add_about(info: Info, input: inputs.AddToCallInput) -> tuple[models.Call, bool]:
    """Turn the call to these structures; says whether anything changed."""
    call = models.Call.objects.get(id=input.call, organization=info.context.request.organization)
    # Each once, in the order given.
    wanted = list({structure.id: structure for structure in _structures(input.about)}.values())
    order = list(models.Call.about.through.objects.filter(call_id=call.id).order_by("id").values_list("structure_id", flat=True))
    if order[-len(wanted) :] == [structure.id for structure in wanted]:
        return call, False
    # Nothing the call was about is lost: the new ones go last, and one it
    # was about before moves there, as what it has turned back to.
    call.about.remove(*[structure for structure in wanted if structure.id in order])
    _append_about(call, wanted)
    return call, True


async def add_to_call(info: Info, input: inputs.AddToCallInput) -> types.Call:
    """The call turns to these structures, keeping what it was about; its open apps hear of it."""
    if not input.about:
        raise ValueError("Name something to add to the call")
    call, changed = await _add_about(info, input)
    if changed:
        await call_channel.abroadcast(CallSignal(update=call.id), [call_group(call.organization_id)])
        logger.info("Call %s turned to %d structures", call.id, len(input.about))
    return call


async def join_call(info: Info, input: inputs.JoinCallInput) -> str:
    """A token to publish and subscribe in the call's room.

    Scoped first: a call of another organization does not exist for this
    caller. The identity carries a nonce so a second window of the same user
    joins beside the first instead of replacing it; the name and metadata
    are what the others see and group by. The name is the token's
    preferred username (authentikate keeps it on ``first_name``); ``username``
    is the issuer-and-sub artifact, not what anyone calls the user.
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
        .with_name(user.first_name or user.username)
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
