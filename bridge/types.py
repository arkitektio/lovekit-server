import datetime
from typing import Any

import kante
import strawberry
import strawberry_django
from arkitekt_service.collaborations.guests import object_scope
from authentikate.strawberry.types import Client, User
from django.db.models import QuerySet
from kante.types import Info
from strawberry.scalars import JSON

from bridge import calls, enums, filters, models, streams

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


@strawberry_django.type(
    models.Agent,
    filters=filters.AgentFilter,
    pagination=True,
    description="An app instance that owns live streams: one per client, user and organization",
)
class Agent:
    @classmethod
    def get_queryset(
        cls, queryset: QuerySet[models.Agent], info: Info, **kwargs: Any
    ) -> QuerySet[models.Agent]:
        """Restrict every read of this type to the request's organization; at a root field, a
        guest's to what is in their collaborations."""
        return object_scope(
            queryset.filter(organization=info.context.request.organization), info=info
        )

    id: strawberry.ID
    client: Client
    user: User
    created_at: datetime.datetime
    streams: list["Stream"] = strawberry_django.field(
        description="Every stream the agent offers, as it declared them last"
    )

    @strawberry_django.field(
        only=["client__name", "client__client_id"],
        description="What the agent is called: its client's name, or its client id.",
    )
    def name(self) -> str:
        return self.client.name or self.client.client_id

    @strawberry.field(description="The LiveKit room the agent's streams are tracks in.")
    def room_name(self) -> str:
        return self.room_name

    @strawberry_django.field(
        only=["id"],
        description="Whether the agent publishes any of its streams right now.",
    )
    async def live(self, info: Info) -> bool:
        return bool(
            await streams.tracks_loader(info.context).load(_agent_room(self.id))
        )


@strawberry.type(
    description="What it takes to reach an agent's streams or a call: the carrier, and what lets the caller in. Where the carrier is, the client knows from its own configuration"
)
class Connection:
    transport: enums.Transport
    credential: str = strawberry.field(
        description="What lets the caller in: for LIVEKIT, the access token of its room"
    )


@strawberry.type(description="One axis of a data stream's frames")
class Axis:
    name: str
    type: enums.AxisType


@strawberry.type(
    description="What a step along one axis measures: position = offset + scale * index, in unit"
)
class Calibration:
    axis: str
    unit: str
    scale: float
    offset: float


@strawberry.type(description="What every frame of a data stream holds")
class DataFormat:
    dtype: str = strawberry.field(
        description="The type of one value, as numpy names it"
    )
    shape: list[int]
    axes: list[Axis] = strawberry.field(
        description="One axis per dimension of the shape, in its order"
    )
    calibration: list[Calibration]
    unit: str | None = strawberry.field(description="The unit of the values themselves")
    reference: str | None = strawberry.field(
        description="The space the axes are in, named as mikro names a coordinate system's reference"
    )


@strawberry_django.type(
    models.Stream,
    filters=filters.StreamFilter,
    order=filters.StreamOrder,
    pagination=True,
    description="One live source an agent offers: a camera, a detector, a microphone, a spectrometer",
)
class Stream:
    @classmethod
    def get_queryset(
        cls, queryset: QuerySet[models.Stream], info: Info, **kwargs: Any
    ) -> QuerySet[models.Stream]:
        """Restrict every read of this type to the request's organization; at a root field, a
        guest's to what is in their collaborations."""
        return object_scope(
            queryset.filter(agent__organization=info.context.request.organization),
            info=info,
        )

    id: strawberry.ID
    key: str = strawberry_django.field(
        description="The agent's name for the stream, the same across its restarts: the name of the LiveKit track it is published as"
    )
    title: str
    kind: enums.StreamKind
    description: str | None
    created_at: datetime.datetime
    agent: Agent
    descriptors: JSON = kante.django_field(
        resolver=resolve_descriptors,
        only=["stored_descriptors", "kind"],
        description=DESCRIPTORS_DESCRIPTION,
    )

    @strawberry_django.field(
        only=["format"], description="What a frame holds; only a data stream has one."
    )
    def format(self) -> DataFormat | None:
        stored = self.format
        if stored is None:
            return None
        return DataFormat(
            dtype=stored["dtype"],
            shape=stored["shape"],
            axes=[
                Axis(name=axis["name"], type=enums.AxisType(axis["type"]))
                for axis in stored["axes"]
            ],
            calibration=[
                Calibration(**calibration) for calibration in stored["calibration"]
            ],
            unit=stored["unit"],
            reference=stored["reference"],
        )

    @strawberry_django.field(
        only=["agent_id", "key"],
        description="Whether the agent publishes this stream right now: LiveKit's answer, asked when read.",
    )
    async def live(self, info: Info) -> bool:
        return self.key in await streams.tracks_loader(info.context).load(
            _agent_room(self.agent_id)
        )


@strawberry_django.type(
    models.Structure, description="A reference to an object on another service"
)
class Structure:
    identifier: str
    object: int


@strawberry.type(description="Someone in a live call, as LiveKit reports them")
class CallParticipant:
    identity: str
    name: str
    joined_at: int


@strawberry_django.type(
    models.Call, filters=filters.CallFilter, order=filters.CallOrder, pagination=True
)
class Call:
    """A multi-party LiveKit room about some structures."""

    @classmethod
    def get_queryset(
        cls, queryset: QuerySet[models.Call], info: Info, **kwargs: Any
    ) -> QuerySet[models.Call]:
        """Restrict every read of this type to the request's organization. A call is in no
        collaboration (it is not a structure lovekit hosts): a guest sees none."""
        return object_scope(
            queryset.filter(organization=info.context.request.organization), info=info
        )

    id: strawberry.ID
    title: str
    created_at: datetime.datetime
    creator: User | None
    ended_at: datetime.datetime | None = strawberry_django.field(
        description="When the call's room last closed, everyone gone; null while it is live (or was never seen to end)"
    )

    @strawberry_django.field(
        description="The structures this call is about, oldest first: the last one is what it turned to most recently."
    )
    def about(self) -> list[Structure]:
        # In the order they were added, which only the link rows know: the
        # relation itself has no order, and a structure's own id says when
        # anything was first called about, not when this call took it on.
        links = (
            models.Call.about.through.objects.filter(call_id=self.id)
            .select_related("structure")
            .order_by("id")
        )
        return [link.structure for link in links]

    @strawberry.field(description="The LiveKit room this call's participants join.")
    def room_name(self) -> str:
        return self.livekit_room_name

    @strawberry.field(
        description="Who is in the call right now. Empty when nobody is: a call is live while LiveKit holds its room."
    )
    async def participants(self) -> list[CallParticipant]:
        return [
            CallParticipant(identity=p.identity, name=p.name, joined_at=p.joined_at)
            for p in await calls.participants(self.livekit_room_name)
        ]

    @strawberry.field(description="How many are in the call right now.")
    async def participant_count(self) -> int:
        return len(await calls.participants(self.livekit_room_name))


@strawberry_django.type(
    models.CallInvite, description="Someone asking someone else into a call"
)
class CallInvite:
    @classmethod
    def get_queryset(
        cls, queryset: QuerySet[models.CallInvite], info: Info, **kwargs: Any
    ) -> QuerySet[models.CallInvite]:
        """Only the caller's own invitations, in their organization."""
        request = info.context.request
        return object_scope(
            queryset.filter(
                invitee=request.user, call__organization=request.organization
            ),
            info=info,
        )

    id: strawberry.ID
    call: Call
    inviter: User
    invitee: User
    created_at: datetime.datetime
