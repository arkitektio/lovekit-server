import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from asgiref.sync import sync_to_async
from authentikate.strawberry.types import Client, User
from bridge import calls, enums, filters, models
from kante.types import Info


@strawberry_django.type(models.Streamer, filters=filters.StreamerFilter, pagination=True)
class Streamer:
    id: strawberry.ID
    user: User
    client: Client
    solo_broadcasts: Optional["SoloBroadcast"] = strawberry_django.field(
        description="The solo broadcasts created by this agent, if any."
    )
    collaborative_broadcasts: List["CollaborativeBroadcast"] = strawberry_django.field(
        description="The collaborative broadcasts created by this agent."
    )



@strawberry_django.type(models.Stream, filters=filters.StreamFilter,  pagination=True)
class Stream:
    id: strawberry.ID
    kind: enums.StreamKind
    streamer: Streamer
    title: str


@strawberry_django.type(models.SoloBroadcast, filters=filters.SoloBroadcastFilter, pagination=True)
class SoloBroadcast:
    id: strawberry.ID
    title: str
    created_at: datetime.datetime
    streamer: Streamer

    @strawberry.field
    def video_streams(self) -> List[Stream]:
        return self.streams.filter(kind=enums.StreamKind.VIDEO)
    
    @strawberry.field
    def audio_streams(self) -> List[Stream]:
        return self.streams.filter(kind=enums.StreamKind.AUDIO)
    
    
    
@strawberry_django.type(models.CollaborativeBroadcast, filters=filters.CollaborativeBroadcastFilter, pagination=True)
class CollaborativeBroadcast:
    id: strawberry.ID
    title: str
    created_at: datetime.datetime
    streamers: List[Streamer] = strawberry_django.field(
        description="The streamers that are collaborating on this broadcast."
    )

    @strawberry.field
    def streams(self) -> List[Stream]:
        return Stream.objects.filter(agent__in=self.streamers, kind=enums.StreamKind.VIDEO)
    
    
    @strawberry.field
    def video_streams(self) -> List[Stream]:
        return self.streamer.streams.filter(kind=enums.StreamKind.VIDEO)
    
    @strawberry.field
    def audio_streams(self) -> List[Stream]:
        return self.streamer.streams.filter(kind=enums.StreamKind.AUDIO)


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
        """Restrict every read of this type to the request's organization."""
        return queryset.filter(organization=info.context.request.organization)

    id: strawberry.ID
    title: str
    created_at: datetime.datetime
    creator: Optional[User]
    about: List[Structure] = strawberry_django.field(description="The structures this call is about.")

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
        return queryset.filter(invitee=request.user, call__organization=request.organization)

    id: strawberry.ID
    call: Call
    inviter: User
    invitee: User
    created_at: datetime.datetime
