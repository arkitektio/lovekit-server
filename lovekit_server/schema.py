import strawberry
from lovekit_server.logs import QuietErrorsSchema
from strawberry_django.optimizer import DjangoOptimizerExtension
from bridge import types, models
from bridge.graphql import mutations, subscriptions
import strawberry_django
from koherent.strawberry.extension import KoherentExtension
from authentikate.strawberry.extension import AuthentikateExtension
from typing import List
from kante.types import Info
import kante


@strawberry.type
class Query:
    """The root query type"""

    streams: List[types.Stream] = strawberry_django.field(description="Get a stream")
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

    calls: List[types.Call] = strawberry_django.field(description="The organization's calls; filter `live` for the ones in progress")

    @strawberry_django.field(description="Get a call by ID")
    def call(self, info: Info, id: strawberry.ID) -> types.Call:
        """A call of the caller's organization."""
        return models.Call.objects.get(id=id, organization=info.context.request.organization)

    @strawberry_django.field(description="Your pending invitations to calls that are still live")
    async def my_call_invites(self, info: Info) -> List[types.CallInvite]:
        """Pending, in this organization, and the call's room still up."""
        from bridge import calls

        request = info.context.request
        live = await calls.live_room_names()
        pending = models.CallInvite.objects.filter(
            invitee=request.user, call__organization=request.organization, dismissed_at__isnull=True
        ).select_related("call", "inviter", "invitee").order_by("-created_at")
        return [invite async for invite in pending if invite.call.livekit_room_name in live]


@strawberry.type
class Mutation:
    """The root mutation type"""

    # Broadcast-related mutations
    ensure_solo_broadcast: types.SoloBroadcast = strawberry_django.field(resolver=mutations.ensure_solo_broadcast, description="Create a solo broadcast")
    ensure_collaborative_broadcast: types.CollaborativeBroadcast = strawberry_django.field(resolver=mutations.ensure_collaborative_broadcast, description="Create a collaborative broadcast")

    # Stream-related mutations
    ensure_stream: str = strawberry_django.field(resolver=mutations.ensure_stream, description="Create a stream and return the token for it")

    join_broadcast: str = strawberry_django.field(resolver=mutations.join_broadcast, description="Join a solo broadcast and return the token for it")

    # Calls: multi-party rooms about structures
    ensure_call: types.Call = strawberry_django.field(resolver=mutations.ensure_call, description="The live call about these structures, or a new one")
    join_call: str = strawberry_django.field(resolver=mutations.join_call, description="Join a call and return the token for it")
    invite_to_call: types.Call = strawberry_django.field(resolver=mutations.invite_to_call, description="Ask users into a call; their open apps ring")
    dismiss_call_invite: strawberry.ID = strawberry_django.field(resolver=mutations.dismiss_call_invite, description="Put an invitation away, on every device")


@strawberry.type
class Subscription:
    """The root subscription type"""

    streams = strawberry.subscription(
        resolver=subscriptions.streams,
        description="Subscribe to stream events",
    )
    call_invites = strawberry.subscription(
        resolver=subscriptions.call_invites,
        description="Your invitations to calls as they arrive and go away",
    )


class Schema(QuietErrorsSchema, kante.Schema):
    """kante.Schema, logging expected resolver errors as one line and bugs with a traceback (see logs.py)."""


schema = Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    schema_directives=[],
    extensions=[DjangoOptimizerExtension, AuthentikateExtension, KoherentExtension],
)
