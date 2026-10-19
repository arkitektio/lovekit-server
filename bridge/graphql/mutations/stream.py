"""An agent declaring its streams, publishing them, and others watching.

An agent (one client, user and organization) declares every stream it offers on every
start: ``declareStreams`` is the whole set. A stream it declared before keeps its row and its
id, one it leaves out is removed, and a start that declares what it declared last time writes
nothing at all, so the organization hears only of real changes (the ``streams``
subscription). ``publishToken`` lets the agent into its own room as its one publisher;
``watchStream`` and ``watchAgent`` let anyone of the organization in to watch.
"""

import logging

from asgiref.sync import sync_to_async
from django.db import transaction
from kante.types import Info

from bridge import calls, inputs, models, tokens, types
from bridge.channel_signals import StreamSignal
from bridge.channels import stream_channel
from lovekit_server.service import service  # noqa: F401 - it binds the models this module writes (descriptors, signals)

logger = logging.getLogger(__name__)


def stream_group(organization) -> str:
    """The channel group an organization's apps listen on for streams. One definition, both sides.

    Spelled by hand for the reason ``call_group`` is: a channel-layer group name may not
    hold the colons ``org_group`` joins with.
    """
    organization_id = getattr(organization, "id", organization)
    return f"streams.org{organization_id}"


def _validate(input: inputs.DeclareStreamsInput) -> None:
    keys = [stream.key for stream in input.streams]
    if any(not key.strip() for key in keys):
        raise ValueError("Every stream needs a key")
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"Each stream is declared once; declared more than once: {', '.join(duplicates)}")


@sync_to_async
def _declare(info: Info, input: inputs.DeclareStreamsInput) -> tuple[models.Agent, list[StreamSignal]]:
    """Make the agent's streams the declared ones; returns what changed, to announce after commit."""
    request = info.context.request
    with transaction.atomic():
        agent, _ = models.Agent.objects.get_or_create(client=request.client, user=request.user, organization=request.organization)
        # Two processes declaring for one agent at once take turns: the second sees the
        # first one's rows instead of creating them a second time.
        agent = models.Agent.objects.select_for_update().get(id=agent.id)
        existing = {stream.key: stream for stream in agent.streams.all()}

        signals: list[StreamSignal] = []
        for declared in input.streams:
            fields = {"title": declared.title or declared.key, "kind": declared.kind.value, "description": declared.description}
            stream = existing.pop(declared.key, None)
            if stream is None:
                stream = models.Stream.objects.create(agent=agent, key=declared.key, **fields)
                signals.append(StreamSignal(create=stream.id))
                continue
            changed = [name for name, value in fields.items() if getattr(stream, name) != value]
            if changed:
                for name in changed:
                    setattr(stream, name, fields[name])
                stream.save(update_fields=changed)
                signals.append(StreamSignal(update=stream.id))

        for stream in existing.values():
            signals.append(StreamSignal(delete=stream.id))
            stream.delete()
    return agent, signals


async def declare_streams(info: Info, input: inputs.DeclareStreamsInput) -> list[types.Stream]:
    """The caller's agent offers exactly these streams; returns them, in the order declared."""
    _validate(input)
    agent, signals = await _declare(info, input)
    # The room is up before anyone hears of a stream in it.
    await calls.create_room(agent.room_name)
    for signal in signals:
        await stream_channel.abroadcast(signal, [stream_group(agent.organization_id)])
    if signals:
        logger.info("Agent %s declared %d streams (%d changes)", agent.id, len(input.streams), len(signals))
    order = {declared.key: index for index, declared in enumerate(input.streams)}
    streams = [stream async for stream in models.Stream.objects.filter(agent=agent).select_related("agent")]
    return sorted(streams, key=lambda stream: order[stream.key])


async def publish_token(info: Info) -> str:
    """A token for the caller's agent to publish its streams into its room.

    Every token of an agent joins as the same participant (``agent-<id>``): a restarted
    process replaces the connection its predecessor left behind instead of publishing every
    stream a second time beside it.
    """
    request = info.context.request
    try:
        agent = await models.Agent.objects.aget(client=request.client, user=request.user, organization=request.organization)
    except models.Agent.DoesNotExist:
        raise ValueError("This app has declared no streams here: call declareStreams first") from None
    await calls.create_room(agent.room_name)
    return tokens.participant_token(
        agent.room_name,
        kind="agent",
        id=agent.id,
        user=request.user,
        can_publish=True,
        can_publish_data=True,
        metadata={"agent": agent.id},
        stable=True,
    )


def _watch_token(info: Info, agent: models.Agent) -> str:
    # Its own identity per token: the same user watching in a second window or on a
    # second device joins beside the first instead of kicking it out.
    user = info.context.request.user
    return tokens.participant_token(agent.room_name, kind="user", id=user.id, user=user, can_publish=False)


async def watch_stream(info: Info, input: inputs.WatchStreamInput) -> str:
    """A token to watch a stream: subscribe to its agent's room, where it is the track named by its key.

    Scoped first: a stream of another organization does not exist for this caller.
    """
    stream = await models.Stream.objects.select_related("agent").aget(id=input.stream, agent__organization=info.context.request.organization)
    await calls.create_room(stream.agent.room_name)
    return _watch_token(info, stream.agent)


async def watch_agent(info: Info, input: inputs.WatchAgentInput) -> str:
    """A token to watch every stream of an agent at once."""
    agent = await models.Agent.objects.aget(id=input.agent, organization=info.context.request.organization)
    await calls.create_room(agent.room_name)
    return _watch_token(info, agent)
