import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from asgiref.sync import sync_to_async
import kante
from arkitekt_service.collaborations.guests import object_scope
from authentikate.strawberry.types import Client, User
from bridge import calls, enums, filters, models, streams
from kante.types import Info
from strawberry.scalars import JSON


DESCRIPTORS_DESCRIPTION = (
    "This object's descriptors, a flat mapping of key to value: the facts about it that an action's port can `require` and a trigger can test "
    "(e.g. `@lovekit/stream_kind`). The keys are the ones lovekit declares for this structure, and the values are the ones a signal about the object carries. "
    "Empty for a structure that declares none"
)


def resolve_descriptors(root) -> JSON:  # noqa: ANN001 - the model instance behind any hosted type
    """The descriptors of a hosted object, from its structure's declaration (``lovekit_server.service``)."""
    from lovekit_server.service import service  # the declaration imports bridge.models

    return service.describe(root)


def _agent_room(agent_id: int) -> tuple[str, str]:
    """The agent's room and the identity it publishes as there (``models.Agent``)."""
    return f"agent-{agent_id}", f"agent-{agent_id}"


@strawberry_django.type(models.Agent, filters=filters.AgentFilter, pagination=True, description="An app instance that owns live streams: one per client, user and organization")
class Agent:
    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Restrict every read of this type to the request's organization; at a root field, a
        guest's to what is in their collaborations."""
        return object_scope(queryset.filter(organization=info.context.request.organization), info=info)

    id: strawberry.ID
    client: Client
    user: User
    created_at: datetime.datetime
    streams: List["Stream"] = strawberry_django.field(description="Every stream the agent offers, as it declared them last")

    @strawberry_django.field(only=["client__name", "client__client_id"], description="What the agent is called: its client's name, or its client id.")
    def name(self) -> str:
        return self.client.name or self.client.client_id

    @strawberry.field(description="The LiveKit room the agent's streams are tracks in.")
    def room_name(self) -> str:
        return self.room_name

    @strawberry_django.field(only=["id"], description="Whether the agent publishes any of its streams right now.")
    async def live(self, info: Info) -> bool:
        return bool(await streams.tracks_loader(info.context).load(_agent_room(self.id)))


@strawberry_django.type(models.Stream, filters=filters.StreamFilter, order=filters.StreamOrder, pagination=True, description="One live source an agent offers: a camera, a detector, a microphone")
class Stream:
    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Restrict every read of this type to the request's organization; at a root field, a
        guest's to what is in their collaborations."""
        return object_scope(queryset.filter(agent__organization=info.context.request.organization), info=info)

    id: strawberry.ID
    key: str = strawberry_django.field(description="The agent's name for the stream, the same across its restarts: the name of the LiveKit track it is published as")
    title: str
    kind: enums.StreamKind
    description: Optional[str]
    created_at: datetime.datetime
    agent: Agent
    descriptors: JSON = kante.django_field(resolver=resolve_descriptors, only=["stored_descriptors", "kind"], description=DESCRIPTORS_DESCRIPTION)

    @strawberry_django.field(only=["agent_id", "key"], description="Whether the agent publishes this stream right now: LiveKit's answer, asked when read.")
    async def live(self, info: Info) -> bool:
        return self.key in await streams.tracks_loader(info.context).load(_agent_room(self.agent_id))


@strawberry_django.type(models.Structure, description="A reference to an object on another service")
class Structure:
    identifier: str
    object: int


@strawberry.type(description="Someone in a live call, as LiveKit reports them")
class CallParticipant:
    identity: str
    name: str
    joined_at: int


@strawberry_django.type(models.Call, filters=filters.CallFilter, order=filters.CallOrder, pagination=True)
class Call:
    """A multi-party LiveKit room about some structures."""

    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Restrict every read of this type to the request's organization. A call is in no
        collaboration (it is not a structure lovekit hosts): a guest sees none."""
        return object_scope(queryset.filter(organization=info.context.request.organization), info=info)

    id: strawberry.ID
    title: str
    created_at: datetime.datetime
    creator: Optional[User]

    @strawberry_django.field(description="The structures this call is about, oldest first: the last one is what it turned to most recently.")
    def about(self) -> List[Structure]:
        # In the order they were added, which only the link rows know: the
        # relation itself has no order, and a structure's own id says when
        # anything was first called about, not when this call took it on.
        links = models.Call.about.through.objects.filter(call_id=self.id).select_related("structure").order_by("id")
        return [link.structure for link in links]

    @strawberry.field(description="The LiveKit room this call's participants join.")
    def room_name(self) -> str:
        return self.livekit_room_name

    @strawberry.field(description="Who is in the call right now. Empty when nobody is: a call is live while LiveKit holds its room.")
    async def participants(self) -> List[CallParticipant]:
        return [
            CallParticipant(identity=p.identity, name=p.name, joined_at=p.joined_at)
            for p in await calls.participants(self.livekit_room_name)
        ]

    @strawberry.field(description="How many are in the call right now.")
    async def participant_count(self) -> int:
        return len(await calls.participants(self.livekit_room_name))


@strawberry_django.type(models.CallInvite, description="Someone asking someone else into a call")
class CallInvite:
    @classmethod
    def get_queryset(cls, queryset, info, **kwargs):
        """Only the caller's own invitations, in their organization."""
        request = info.context.request
        return object_scope(queryset.filter(invitee=request.user, call__organization=request.organization), info=info)

    id: strawberry.ID
    call: Call
    inviter: User
    invitee: User
    created_at: datetime.datetime
