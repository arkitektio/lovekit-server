import strawberry
from lovekit_server.logs import QuietErrorsSchema
from strawberry_django.optimizer import DjangoOptimizerExtension
from bridge import types, models
from bridge.graphql import mutations, subscriptions
import strawberry_django
from koherent.strawberry.extension import KoherentExtension
from authentikate.strawberry.extension import AuthentikateExtension
from authentikate.strawberry import AuthExtension
from arkitekt_service.collaborations import graphql as collaboration_types
from arkitekt_service.collaborations.guests import object_scope
from arkitekt_service.graphql import CollaborationGate, annotate_schema
from django.db.models import Model
from typing import List
from kante.types import Info
import kante
from lovekit_server.service import service as lovekit_service


#: How each hosted model reaches its organization.
_ORGANIZATION_PATH: dict[type[Model], str] = {models.Agent: "organization", models.Stream: "agent__organization"}


def _in_organization(model: type[Model], id: strawberry.ID, info: Info) -> Model:
    """An agent or a stream of the request's organization, by ID."""
    return model._default_manager.get(**{"id": id, _ORGANIZATION_PATH[model]: info.context.request.organization})


#: The collaborations of lovekit's agents and streams, which a guest of the organization is granted.
collaboration_api = collaboration_types.resolvers(fetch=_in_organization)


@strawberry.type
class Query:
    """The root query type"""

    streams: List[types.Stream] = strawberry_django.field(description="The streams of the organization's agents; filter `live` for the ones being published")
    agents: List[types.Agent] = strawberry_django.field(description="The organization's agents that offer streams")

    @strawberry_django.field(description="Get a stream by ID")
    def stream(self, info: Info, id: strawberry.ID) -> types.Stream:
        """A stream of an agent of the caller's organization (a guest's: in their collaborations)."""
        return object_scope(models.Stream.objects.filter(agent__organization=info.context.request.organization), info=info).get(id=id)

    @strawberry_django.field(description="Get an agent by ID")
    def agent(self, info: Info, id: strawberry.ID) -> types.Agent:
        """An agent of the caller's organization (a guest's: in their collaborations)."""
        return object_scope(models.Agent.objects.filter(organization=info.context.request.organization), info=info).get(id=id)

    calls: List[types.Call] = strawberry_django.field(description="The organization's calls; filter `live` for the ones in progress")

    @strawberry_django.field(description="Get a call by ID")
    def call(self, info: Info, id: strawberry.ID) -> types.Call:
        """A call of the caller's organization (none for a guest: a call is in no collaboration)."""
        return object_scope(models.Call.objects.filter(organization=info.context.request.organization), info=info).get(id=id)

    @strawberry_django.field(description="Your pending invitations to calls that are still live")
    async def my_call_invites(self, info: Info) -> List[types.CallInvite]:
        """Pending, in this organization, and the call's room still up."""
        from bridge import calls

        request = info.context.request
        live = await calls.live_room_names()
        pending = object_scope(models.CallInvite.objects.filter(
            invitee=request.user, call__organization=request.organization, dismissed_at__isnull=True
        ), info=info).select_related("call", "inviter", "invitee").order_by("-created_at")
        return [invite async for invite in pending if invite.call.livekit_room_name in live]

    collaborations: List[collaboration_types.Collaboration] = strawberry_django.field(resolver=collaboration_api.collaborations, description="List the organization's collaborations: what a guest granted one sees of it (a guest: the collaborations granted to them)")
    collaboration: collaboration_types.Collaboration = strawberry_django.field(resolver=collaboration_api.collaboration, description="Get a single collaboration by ID")


@strawberry.type
class Mutation:
    """The root mutation type"""

    # Collaborations: what a guest of the organization is granted to see; made by its admins and editors, never a guest
    create_collaboration: collaboration_types.Collaboration = strawberry_django.field(extensions=[AuthExtension(any_role_of=["admin", "editor"])], resolver=collaboration_api.create_collaboration, description="Create an empty collaboration, to put agents and streams in and grant a guest")
    add_to_collaboration: collaboration_types.Collaboration = strawberry_django.field(extensions=[AuthExtension(any_role_of=["admin", "editor"])], resolver=collaboration_api.add_to_collaboration, description="Put an agent or a stream in a collaboration: an agent brings every stream it offers")
    remove_from_collaboration: collaboration_types.Collaboration = strawberry_django.field(extensions=[AuthExtension(any_role_of=["admin", "editor"])], resolver=collaboration_api.remove_from_collaboration, description="Take an agent or a stream out of a collaboration")
    delete_collaboration: strawberry.ID = strawberry_django.field(extensions=[AuthExtension(any_role_of=["admin", "editor"])], resolver=collaboration_api.delete_collaboration, description="Delete a collaboration: whoever was granted it sees nothing of it any more")

    # Agent streams: what an app instance offers live, its own and nobody else's
    declare_streams: List[types.Stream] = strawberry_django.field(resolver=mutations.declare_streams, description="Offer exactly these streams as the caller's agent: undeclared ones are removed, unchanged ones untouched")
    publish_token: str = strawberry_django.field(resolver=mutations.publish_token, description="A token for the caller's agent to publish its streams; a newer connection replaces an older one")
    # Watching is open to a guest who has the agent in a collaboration: a token opens the agent's whole room
    watch_stream: str = strawberry_django.field(resolver=mutations.watch_stream, extensions=[AuthExtension(allow_scoped=True)], description="A token to watch a stream: its agent's room, where it is the track named by its key. A guest needs the agent in one of their collaborations")
    watch_agent: str = strawberry_django.field(resolver=mutations.watch_agent, extensions=[AuthExtension(allow_scoped=True)], description="A token to watch every stream of an agent. A guest needs the agent in one of their collaborations")

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
    extensions=[
        DjangoOptimizerExtension,
        AuthentikateExtension,
        # A guest of the organization is handed only what is in their collaborations.
        CollaborationGate,
        KoherentExtension,
    ],
)

# Which structure each type is (`@identified`), and, behind the gate, that lovekit lets guests in.
annotate_schema(schema, lovekit_service)
