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