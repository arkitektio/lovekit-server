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
    
    @strawberry_django.field(
        description="Get a stream by ID",
    )
    def stream(self, id: strawberry.ID) -> types.Stream:
        """Get a stream by ID"""
        return models.Stream.objects.get(id=id)


@strawberry.type
class Mutation:
    """The root mutation type"""

    create_video_stream: types.Stream = strawberry_django.field(
        resolver=mutations.create_video_stream, description="Create a stream"
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
