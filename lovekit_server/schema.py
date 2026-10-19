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

    streams: List[types.Stream] = strawberry_django.field(description="The streams of the organization's agents; filter `live` for the ones being published")
    agents: List[types.Agent] = strawberry_django.field(description="The organization's agents that offer streams")

    @strawberry_django.field(description="Get a stream by ID")
    def stream(self, info: Info, id: strawberry.ID) -> types.Stream:
        """A stream of an agent of the caller's organization."""
        return models.Stream.objects.get(id=id, agent__organization=info.context.request.organization)

    @strawberry_django.field(description="Get an agent by ID")
    def agent(self, info: Info, id: strawberry.ID) -> types.Agent:
        """An agent of the caller's organization."""
        return models.Agent.objects.get(id=id, organization=info.context.request.organization)

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

    # Agent streams: what an app instance offers live, its own and nobody else's
    declare_streams: List[types.Stream] = strawberry_django.field(resolver=mutations.declare_streams, description="Offer exactly these streams as the caller's agent: undeclared ones are removed, unchanged ones untouched")
    publish_token: str = strawberry_django.field(resolver=mutations.publish_token, description="A token for the caller's agent to publish its streams; a newer connection replaces an older one")
    watch_stream: str = strawberry_django.field(resolver=mutations.watch_stream, description="A token to watch a stream: its agent's room, where it is the track named by its key")
    watch_agent: str = strawberry_django.field(resolver=mutations.watch_agent, description="A token to watch every stream of an agent")

    # Calls: multi-party rooms about structures
    ensure_call: types.Call = strawberry_django.field(resolver=mutations.ensure_call, description="The live call about these structures, or a new one")
    add_to_call: types.Call = strawberry_django.field(resolver=mutations.add_to_call, description="Turn a call to these structures: they become what it is about last, and what it was about stays")
    join_call: str = strawberry_django.field(resolver=mutations.join_call, description="Join a call and return the token for it")
    invite_to_call: types.Call = strawberry_django.field(resolver=mutations.invite_to_call, description="Ask users into a call; their open apps ring")
    dismiss_call_invite: strawberry.ID = strawberry_django.field(resolver=mutations.dismiss_call_invite, description="Put an invitation away, on every device")


@strawberry.type
class Subscription:
    """The root subscription type"""

    streams = strawberry.subscription(
        resolver=subscriptions.streams,
        description="Streams your organization's agents declare, change and drop, as they do",
    )
    call_invites = strawberry.subscription(
        resolver=subscriptions.call_invites,
        description="Your invitations to calls as they arrive and go away",
    )
    calls = strawberry.subscription(
        resolver=subscriptions.calls,
        description="The calls others start in your organization as they start, and any call's new topics",
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
