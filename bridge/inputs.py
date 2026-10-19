import strawberry
from bridge import enums


@strawberry.input(description="One stream an agent offers")
class StreamDeclarationInput:
    key: str = strawberry.field(description="The agent's own name for the stream, the same on every start; its LiveKit track is published under this name")
    title: str | None = strawberry.field(default=None, description="What the stream is called; the key when not given")
    kind: enums.StreamKind = strawberry.field(default=enums.StreamKind.VIDEO, description="Whether it is video or audio")
    description: str | None = strawberry.field(default=None, description="What the stream shows")


@strawberry.input(description="Every stream an agent offers")
class DeclareStreamsInput:
    """The whole set: a stream the agent declared before and leaves out here is removed."""

    streams: list[StreamDeclarationInput]


@strawberry.input(description="The stream to watch")
class WatchStreamInput:
    stream: strawberry.ID


@strawberry.input(description="The agent whose streams to watch")
class WatchAgentInput:
    agent: strawberry.ID


@strawberry.input(description="A reference to an object on another service")
class StructureInput:
    identifier: str
    object: int


@strawberry.input(description="The call to find or start")
class EnsureCallInput:
    """What the call is about, and its title."""

    about: list[StructureInput]
    title: str | None = None


@strawberry.input(description="What a call is now also about")
class AddToCallInput:
    """The call, and the structures to add to what it is about."""

    call: strawberry.ID
    about: list[StructureInput]


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
