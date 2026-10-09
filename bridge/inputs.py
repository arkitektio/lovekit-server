import strawberry
from bridge import enums


@strawberry.input
class EnsureSoloBroadcastInput:
    instance_id: str | None = None
    title: str | None = None
    
    

@strawberry.input
class EnsureCollaborativeBroadcastInput:
    instance_id: str | None = None
    title: str | None = None    
    
    
@strawberry.input
class EnsureStreamInput:
    broadcast: strawberry.ID | None = None
    kind: enums.StreamKind = enums.StreamKind.VIDEO
    title: str | None = None
    
    
@strawberry.input
class JoinBroadcastInput:
    broadcast: strawberry.ID
    
    
    
@strawberry.input
class JoinCollaborativeBroadcastInput:
    id: strawberry.ID
    instance_id: str | None = None
    title: str | None = None

@strawberry.input(description="A reference to an object on another service")
class StructureInput:
    identifier: str
    object: int


@strawberry.input(description="The call to find or start")
class EnsureCallInput:
    """What the call is about, and its title."""

    about: list[StructureInput]
    title: str | None = None


@strawberry.input(description="The call to join")
class JoinCallInput:
    call: strawberry.ID


@strawberry.input(description="Who to ask into a call")
class InviteToCallInput:
    call: strawberry.ID
    users: list[strawberry.ID] = strawberry.field(description="The users to invite, by their lok id (the `sub` their token carries)")


@strawberry.input(description="The invitation to put away")
class DismissCallInviteInput:
    id: strawberry.ID
