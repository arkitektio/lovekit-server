import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from authentikate.strawberry.types import Client, User
from bridge import enums, filters, models
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