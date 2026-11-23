from typing import Any

import kante
import strawberry
import strawberry_django
from arkitekt_service.collaborations import graphql as collaboration_types
from arkitekt_service.collaborations.guests import object_scope
from arkitekt_service.graphql import (
    CollaborationGate,
    TelemetryExtension,
    annotate_schema,
)
from authentikate.strawberry import AuthExtension, AuthSubscribeExtension
from authentikate.strawberry.extension import AuthentikateExtension
from django.db.models import Model
from kante.types import Info
from koherent.strawberry.extension import KoherentExtension
from strawberry_django.optimizer import DjangoOptimizerExtension

from bridge import models, types
from bridge.graphql import mutations, subscriptions
from lovekit_server.contract import EDITOR
from lovekit_server.logs import QuietErrorsSchema
from lovekit_server.service import service as lovekit_service

#: How each hosted model reaches its organization.
_ORGANIZATION_PATH: dict[type[Model], str] = {
    models.Agent: "organization",
    models.Stream: "agent__organization",
}


def _in_organization(model: type[Model], id: strawberry.ID, info: Info) -> Model:
    """An agent or a stream of the request's organization, by ID."""
    return model._default_manager.get(
        **{"id": id, _ORGANIZATION_PATH[model]: info.context.request.organization}
    )


#: The collaborations of lovekit's agents and streams, which a guest of the organization is granted.
collaboration_api = collaboration_types.resolvers(fetch=_in_organization)


def field(scope: str = "lovekit_watch", **kwargs: Any) -> Any:  # noqa: ANN401 -- as strawberry_django.field: the value of `x: T = field()`
    "A field an app needs ``scope`` for (``lovekit_watch``, unless it says otherwise)."
    return strawberry_django.field(extensions=[AuthExtension(scopes=[scope])], **kwargs)


def mutation(scope: str, **kwargs: Any) -> Any:  # noqa: ANN401 -- as strawberry_django.field: the value of `x: T = mutation()`
    """A write: an app needs ``scope`` for it, a member ``lovekit_editor`` (``lovekit_admin`` holds every role)."""
    return strawberry_django.field(
        extensions=[AuthExtension(scopes=[scope], any_role_of=[EDITOR])], **kwargs
    )


def watch_mutation(**kwargs: Any) -> Any:  # noqa: ANN401 -- as strawberry_django.field: the value of `x: T = watch_mutation()`
    """A token to watch: a read, open to a guest who has the agent in a collaboration."""
    return strawberry_django.field(
        extensions=[AuthExtension(scopes=["lovekit_watch"], allow_scoped=True)],
        **kwargs,
    )


def subscription(**kwargs: Any) -> strawberry.subscription:
    """A subscription: what it streams is read, so an app needs ``lovekit_watch`` for it."""
    return strawberry.subscription(
        extensions=[AuthSubscribeExtension(scopes=["lovekit_watch"])], **kwargs
    )


@strawberry.type
class Query:
    """The root query type"""

    streams: list[types.Stream] = field(
        description="The streams of the organization's agents; filter `live` for the ones being published"
    )
    agents: list[types.Agent] = field(
        description="The organization's agents that offer streams"
    )

    @field(description="Get a stream by ID")
    def stream(self, info: Info, id: strawberry.ID) -> types.Stream:
        """A stream of an agent of the caller's organization (a guest's: in their collaborations)."""
        return object_scope(
            models.Stream.objects.filter(
                agent__organization=info.context.request.organization
            ),
            info=info,
        ).get(id=id)

    @field(description="Get an agent by ID")
    def agent(self, info: Info, id: strawberry.ID) -> types.Agent:
        """An agent of the caller's organization (a guest's: in their collaborations)."""
        return object_scope(
            models.Agent.objects.filter(organization=info.context.request.organization),
            info=info,
        ).get(id=id)

    calls: list[types.Call] = field(
        description="The organization's calls; filter `live` for the ones in progress"
    )

    @field(description="Get a call by ID")
    def call(self, info: Info, id: strawberry.ID) -> types.Call:
        """A call of the caller's organization (none for a guest: a call is in no collaboration)."""
        return object_scope(
            models.Call.objects.filter(organization=info.context.request.organization),
            info=info,
        ).get(id=id)

    @field(description="Your pending invitations to calls that are still live")
    async def my_call_invites(self, info: Info) -> list[types.CallInvite]:
        """Pending, in this organization, and the call's room still up."""
        from bridge import calls

        request = info.context.request
        live = await calls.live_room_names()
        pending = (
            object_scope(
                models.CallInvite.objects.filter(
                    invitee=request.user,
                    call__organization=request.organization,
                    dismissed_at__isnull=True,
                ),
                info=info,
            )
            .select_related("call", "inviter", "invitee")
            .order_by("-created_at")
        )
        return [
            invite async for invite in pending if invite.call.livekit_room_name in live
        ]

    collaborations: list[collaboration_types.Collaboration] = field(
        resolver=collaboration_api.collaborations,
        description="List the organization's collaborations: what a guest granted one sees of it (a guest: the collaborations granted to them)",
    )
    collaboration: collaboration_types.Collaboration = field(
        resolver=collaboration_api.collaboration,
        description="Get a single collaboration by its key (lok's): what was put in it here",
    )


@strawberry.type
class Mutation:
    """The root mutation type"""

    # Collaborations: what a guest of the organization is granted to see; made by its editors, never a guest
    add_to_collaboration: collaboration_types.Collaboration = mutation(
        scope="lovekit_share",
        resolver=collaboration_api.add_to_collaboration,
        description="Put an agent in a collaboration (lok's, by its key): it brings every stream it offers. The collaboration's row here is made the first time something is put in",
    )
    add_many_to_collaboration: collaboration_types.Collaboration = mutation(
        scope="lovekit_share",
        resolver=collaboration_api.add_many_to_collaboration,
        description="Put several agents in a collaboration (by its key) at once, each with every stream it offers: all of them, or none",
    )
    share_workflow: collaboration_types.WorkflowShare = mutation(
        scope="lovekit_share",
        resolver=collaboration_api.share_workflow,
        description="Put what a workflow (its root task) created in lovekit in a collaboration. Nothing here says which workflow made it: an agent and its streams are the app's, across workflows, so the report lists them as unknown and puts nothing in. `dryRun` only says what would be put in",
    )
    remove_from_collaboration: collaboration_types.Collaboration = mutation(
        scope="lovekit_share",
        resolver=collaboration_api.remove_from_collaboration,
        description="Take an agent out of a collaboration (by its key), and its streams with it",
    )
    delete_collaboration: strawberry.ID = mutation(
        scope="lovekit_share",
        resolver=collaboration_api.delete_collaboration,
        description="Take everything lovekit put in a collaboration (by its key) out of it: whoever was granted it sees nothing of it here any more. lok's collaboration, and its grants, stay",
    )

    # Agent streams: what an app instance offers live, its own and nobody else's
    declare_streams: list[types.Stream] = mutation(
        scope="lovekit_publish",
        resolver=mutations.declare_streams,
        description="Offer exactly these streams as the caller's agent: undeclared ones are removed, unchanged ones untouched",
    )
    publisher_connection: types.Connection = mutation(
        scope="lovekit_publish",
        resolver=mutations.publisher_connection,
        description="What the caller's agent publishes its streams with; a newer connection replaces an older one",
    )
    # Watching is open to a guest who has the agent in a collaboration: a connection opens the agent's whole room
    watch_stream: types.Connection = watch_mutation(
        resolver=mutations.watch_stream,
        description="What a stream is watched with: its agent's room, where it is the track named by its key. A guest needs the agent in one of their collaborations",
    )
    watch_agent: types.Connection = watch_mutation(
        resolver=mutations.watch_agent,
        description="What every stream of an agent is watched with. A guest needs the agent in one of their collaborations",
    )

    # Calls: multi-party rooms about structures
    ensure_call: types.Call = mutation(
        scope="lovekit_call",
        resolver=mutations.ensure_call,
        description="The live call about these structures, or a new one",
    )
    add_to_call: types.Call = mutation(
        scope="lovekit_call",
        resolver=mutations.add_to_call,
        description="Turn a call to these structures: they become what it is about last, and what it was about stays",
    )
    join_call: types.Connection = mutation(
        scope="lovekit_call",
        resolver=mutations.join_call,
        description="Join a call: what its room is reached with",
    )
    invite_to_call: types.Call = mutation(
        scope="lovekit_call",
        resolver=mutations.invite_to_call,
        description="Ask users into a call; their open apps ring",
    )
    dismiss_call_invite: strawberry.ID = mutation(
        scope="lovekit_call",
        resolver=mutations.dismiss_call_invite,
        description="Put an invitation away, on every device",
    )


@strawberry.type
class Subscription:
    """The root subscription type"""

    streams = subscription(
        resolver=subscriptions.streams,
        description="Streams your organization's agents declare, change and drop, as they do",
    )
    call_invites = subscription(
        resolver=subscriptions.call_invites,
        description="Your invitations to calls as they arrive and go away",
    )
    calls = subscription(
        resolver=subscriptions.calls,
        description="The calls others start in your organization as they start, any call's new topics, and calls ending and coming back",
    )
    call_participants = subscription(
        resolver=subscriptions.call_participants,
        description="Who joins and leaves one call, as they do",
    )


class Schema(QuietErrorsSchema, kante.Schema):
    """kante.Schema, logging expected resolver errors as one line and bugs with a traceback (see logs.py)."""


schema = Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    schema_directives=[],
    extensions=[
        TelemetryExtension,
        DjangoOptimizerExtension,
        AuthentikateExtension,
        # A guest of the organization is handed only what is in their collaborations.
        CollaborationGate,
        KoherentExtension,
    ],
)

# Which structure each type is (`@identified`), and, behind the gate, that lovekit lets guests in.
annotate_schema(schema, lovekit_service)
