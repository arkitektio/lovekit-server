import strawberry
from strawberry_django.optimizer import DjangoOptimizerExtension
from bridge import types, models
from bridge.graphql import mutations, subscriptions
import strawberry_django
from koherent.strawberry.extension import KoherentExtension
from authentikate.strawberry.extension import AuthentikateExtension
from typing import List



@strawberry.type
class Query:
    """The root query type"""

    streams: List[types.Stream] = strawberry_django.field(
        description="Get a stream"
    )
    solo_broadcasts: List[types.SoloBroadcast] = strawberry_django.field(
        description="Get all solo broadcasts",
    )
    collaborative_broadcasts: List[types.CollaborativeBroadcast] = strawberry_django.field(
        description="Get all collaborative broadcasts",
    )
    
    @strawberry_django.field(
        description="Get a stream by ID",
    )
    def stream(self, id: strawberry.ID) -> types.Stream:
        """Get a stream by ID"""
        return models.Stream.objects.get(id=id)
    
    @strawberry_django.field(
        description="Get a solo broadcast by ID",
    )
    def solo_broadcast(self, id: strawberry.ID) -> types.SoloBroadcast:
        """Get a solo broadcast by ID"""
        return models.SoloBroadcast.objects.get(id=id)
    
    @strawberry_django.field(
        description="Get a collaborative broadcast by ID",
    )
    def collaborative_broadcast(self, id: strawberry.ID) -> types.CollaborativeBroadcast:
        """Get a collaborative broadcast by ID"""
        return models.CollaborativeBroadcast.objects.get(id=id)
    
    
    


@strawberry.type
class Mutation:
    """The root mutation type"""

    # Broadcast-related mutations
    ensure_solo_broadcast: types.SoloBroadcast = strawberry_django.field(
        resolver=mutations.ensure_solo_broadcast, description="Create a solo broadcast"
    )
    ensure_collaborative_broadcast: types.CollaborativeBroadcast = strawberry_django.field(
        resolver=mutations.ensure_collaborative_broadcast, description="Create a collaborative broadcast"
    )
    
    # Stream-related mutations
    ensure_stream: str = strawberry_django.field(
        resolver=mutations.ensure_stream, description="Create a stream and return the token for it"
    )
    
    join_broadcast: str = strawberry_django.field(
        resolver=mutations.join_broadcast, description="Join a solo broadcast and return the token for it"
    )
    
    


@strawberry.type
class Subscription:
    """The root subscription type"""
    
    streams = strawberry.subscription(
        resolver=subscriptions.streams,
        description="Subscribe to stream events",
    )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    schema_directives=[],
    extensions=[DjangoOptimizerExtension, AuthentikateExtension, KoherentExtension],
)
