"""An agent declaring its streams, publishing them, and others watching.

An agent (one client, user and organization) declares every stream it offers on every
start: ``declareStreams`` is the whole set. A stream it declared before keeps its row and its
id, one it leaves out is removed, and a start that declares what it declared last time writes
nothing at all, so the organization hears only of real changes (the ``streams``
subscription). ``publisherConnection`` lets the agent into its own room as its one publisher;
``watchStream`` and ``watchAgent`` let anyone of the organization in to watch, and a guest of it
who has the agent in one of their collaborations: a watching connection opens the agent's whole
room, so it is the agent that has to be shared, not only the stream.

A data stream declares what a frame holds (``format``). A frame is at most ``MAX_FRAME_BYTES``,
so it is one packet on any carrier.
"""

import logging
import math

import strawberry
from arkitekt_service.collaborations.guests import arequire_in_collaboration, guest_of
from asgiref.sync import sync_to_async
from django.db import transaction
from kante.context import Organization
from kante.types import Info

from bridge import calls, enums, inputs, models, tokens, types
from bridge.channel_signals import StreamSignal
from bridge.channels import stream_channel
from lovekit_server.service import service  # noqa: F401 - it binds the models this module writes (descriptors, signals)

logger = logging.getLogger(__name__)


def stream_group(organization: Organization | int) -> str:
    """The channel group an organization's apps listen on for streams. One definition, both sides.

    Spelled by hand for the reason ``call_group`` is: a channel-layer group name may not
    hold the colons ``org_group`` joins with.
    """
    organization_id = organization if isinstance(organization, int) else organization.id
    return f"streams.org{organization_id}"


#: The most one frame of a data stream holds.
MAX_FRAME_BYTES = 1024

#: The value types a data stream may declare, and the bytes one value takes.
ITEM_SIZES = {
    "uint8": 1,
    "int8": 1,
    "uint16": 2,
    "int16": 2,
    "float16": 2,
    "uint32": 4,
    "int32": 4,
    "float32": 4,
    "float64": 8,
}


def _validate_format(key: str, format: inputs.DataFormatInput) -> None:
    if format.dtype not in ITEM_SIZES:
        raise ValueError(
            f"{key}: {format.dtype} is no value type of a data stream; one of {', '.join(ITEM_SIZES)}"
        )
    if not format.shape or any(size < 1 for size in format.shape):
        raise ValueError(
            f"{key}: a frame's shape names at least one dimension, each of at least one value"
        )
    size = math.prod(format.shape) * ITEM_SIZES[format.dtype]
    if size > MAX_FRAME_BYTES:
        raise ValueError(
            f"{key}: a frame of {size} bytes is more than the {MAX_FRAME_BYTES} a data stream carries; send fewer or smaller values"
        )
    names = [axis.name for axis in format.axes]
    if len(names) != len(format.shape) or len(set(names)) != len(names):
        raise ValueError(
            f"{key}: a format names one axis per dimension of its shape, each once"
        )
    unknown = sorted(
        {calibration.axis for calibration in format.calibration} - set(names)
    )
    if unknown:
        raise ValueError(
            f"{key}: calibrated, but no axis of the format: {', '.join(unknown)}"
        )


def _stored_format(format: inputs.DataFormatInput | None) -> dict | None:
    """A declared format as its row keeps it."""
    if format is None:
        return None
    stored = strawberry.asdict(format)
    stored["axes"] = [
        {"name": axis.name, "type": axis.type.value} for axis in format.axes
    ]
    return stored


def _validate(input: inputs.DeclareStreamsInput) -> None:
    keys = [stream.key for stream in input.streams]
    if any(not key.strip() for key in keys):
        raise ValueError("Every stream needs a key")
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(
            f"Each stream is declared once; declared more than once: {', '.join(duplicates)}"
        )
    for stream in input.streams:
        if stream.kind != enums.StreamKind.DATA:
            if stream.format is not None:
                raise ValueError(f"{stream.key}: only a data stream has a format")
        elif stream.format is None:
            raise ValueError(
                f"{stream.key}: a data stream says what a frame holds (format)"
            )
        else:
            _validate_format(stream.key, stream.format)


@sync_to_async
def _declare(
    info: Info, input: inputs.DeclareStreamsInput
) -> tuple[models.Agent, list[StreamSignal]]:
    """Make the agent's streams the declared ones; returns what changed, to announce after commit."""
    request = info.context.request
    with transaction.atomic():
        agent, _ = models.Agent.objects.get_or_create(
            client=request.client, user=request.user, organization=request.organization
        )
        # Two processes declaring for one agent at once take turns: the second sees the
        # first one's rows instead of creating them a second time.
        agent = models.Agent.objects.select_for_update().get(id=agent.id)
        existing = {stream.key: stream for stream in agent.streams.all()}

        signals: list[StreamSignal] = []
        for declared in input.streams:
            fields = {
                "title": declared.title or declared.key,
                "kind": declared.kind.value,
                "description": declared.description,
                "format": _stored_format(declared.format),
            }
            stream = existing.pop(declared.key, None)
            if stream is None:
                stream = models.Stream.objects.create(
                    agent=agent, key=declared.key, **fields
                )
                signals.append(StreamSignal(create=stream.id))
                continue
            changed = [
                name for name, value in fields.items() if getattr(stream, name) != value
            ]
            if changed:
                for name in changed:
                    setattr(stream, name, fields[name])
                stream.save(update_fields=changed)
                signals.append(StreamSignal(update=stream.id))

        for stream in existing.values():
            signals.append(StreamSignal(delete=stream.id))
            stream.delete()
    return agent, signals


async def declare_streams(
    info: Info, input: inputs.DeclareStreamsInput
) -> list[types.Stream]:
    """The caller's agent offers exactly these streams; returns them, in the order declared."""
    _validate(input)
    agent, signals = await _declare(info, input)
    # The room is up before anyone hears of a stream in it.
    await calls.create_room(agent.room_name)
    for signal in signals:
        await stream_channel.abroadcast(signal, [stream_group(agent.organization_id)])
    if signals:
        logger.info(
            "Agent %s declared %d streams (%d changes)",
            agent.id,
            len(input.streams),
            len(signals),
        )
    order = {declared.key: index for index, declared in enumerate(input.streams)}
    streams = [
        stream
        async for stream in models.Stream.objects.filter(agent=agent).select_related(
            "agent"
        )
    ]
    return sorted(streams, key=lambda stream: order[stream.key])


def _livekit(token: str) -> types.Connection:
    return types.Connection(transport=enums.Transport.LIVEKIT, credential=token)


async def publisher_connection(info: Info) -> types.Connection:
    """What the caller's agent publishes its streams with: into its room.

    Every connection of an agent joins as the same participant (``agent-<id>``): a restarted
    process replaces the connection its predecessor left behind instead of publishing every
    stream a second time beside it.
    """
    request = info.context.request
    try:
        agent = await models.Agent.objects.aget(
            client=request.client, user=request.user, organization=request.organization
        )
    except models.Agent.DoesNotExist:
        raise ValueError(
            "This app has declared no streams here: call declareStreams first"
        ) from None
    await calls.create_room(agent.room_name)
    return _livekit(
        tokens.participant_token(
            agent.room_name,
            kind="agent",
            id=agent.id,
            user=request.user,
            can_publish=True,
            can_publish_data=True,
            can_update_own_metadata=True,
            metadata={"agent": agent.id},
            stable=True,
        )
    )


def _watching(info: Info, agent: models.Agent) -> types.Connection:
    # Its own identity per token: the same user watching in a second window or on a
    # second device joins beside the first instead of kicking it out.
    user = info.context.request.user
    return _livekit(
        tokens.participant_token(
            agent.room_name,
            kind="user",
            id=user.id,
            user=user,
            can_publish=False,
            # Data packets only, for RPC: a member times latency pings to the agent
            # (`lovekit.ping`); its media and data tracks are read from the agent alone.
            # A guest (a collaboration's) sends nothing into the room.
            can_publish_data=guest_of(info) is None,
        )
    )


async def watch_stream(info: Info, input: inputs.WatchStreamInput) -> types.Connection:
    """What a stream is watched with: its agent's room, where it is the track named by its key.

    Scoped first: a stream of another organization does not exist for this caller. A guest
    needs the stream's agent in a collaboration: the connection opens every track there.
    """
    stream = await models.Stream.objects.select_related("agent").aget(
        id=input.stream, agent__organization=info.context.request.organization
    )
    await arequire_in_collaboration(stream.agent, info=info)
    await calls.create_room(stream.agent.room_name)
    return _watching(info, stream.agent)


async def watch_agent(info: Info, input: inputs.WatchAgentInput) -> types.Connection:
    """What every stream of an agent is watched with at once; a guest's, of an agent in their collaborations."""
    agent = await models.Agent.objects.aget(
        id=input.agent, organization=info.context.request.organization
    )
    await arequire_in_collaboration(agent, info=info)
    await calls.create_room(agent.room_name)
    return _watching(info, agent)
