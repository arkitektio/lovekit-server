import strawberry

from bridge import enums


@strawberry.input(
    description="One axis of a data stream's frames: its name and its semantic kind. Units belong to a calibration"
)
class AxisInput:
    name: str = strawberry.field(description="The name of the axis, e.g. 'wavelength'")
    type: enums.AxisType = strawberry.field(description="The semantic kind of the axis")


@strawberry.input(
    description="What a step along one axis measures: position = offset + scale * index, in unit"
)
class CalibrationInput:
    axis: str = strawberry.field(description="The name of the axis this calibrates")
    unit: str = strawberry.field(
        description="The unit of the calibrated position, e.g. 'nm'"
    )
    scale: float = strawberry.field(
        default=1.0, description="The step between two neighbouring values"
    )
    offset: float = strawberry.field(
        default=0.0, description="The position of the first value"
    )


@strawberry.input(description="What every frame of a data stream holds")
class DataFormatInput:
    dtype: str = strawberry.field(
        description="The type of one value, as numpy names it: uint8, int16, float16, float32, ..."
    )
    shape: list[int] = strawberry.field(
        description="The shape of one frame; a frame is at most 1024 bytes"
    )
    axes: list[AxisInput] = strawberry.field(
        description="One axis per dimension of the shape, in its order"
    )
    calibration: list[CalibrationInput] = strawberry.field(
        default_factory=list, description="The axes that measure something, and what"
    )
    unit: str | None = strawberry.field(
        default=None, description="The unit of the values themselves, e.g. 'counts'"
    )
    reference: str | None = strawberry.field(
        default=None,
        description="The space the axes are in, named as mikro names a coordinate system's reference: stored data of the same reference is in the same space",
    )


@strawberry.input(description="One stream an agent offers")
class StreamDeclarationInput:
    key: str = strawberry.field(
        description="The agent's own name for the stream, the same on every start; its LiveKit track is published under this name"
    )
    title: str | None = strawberry.field(
        default=None, description="What the stream is called; the key when not given"
    )
    kind: enums.StreamKind = strawberry.field(
        default=enums.StreamKind.VIDEO, description="Whether it is video, audio or data"
    )
    description: str | None = strawberry.field(
        default=None, description="What the stream shows"
    )
    format: DataFormatInput | None = strawberry.field(
        default=None,
        description="What a frame holds: needed for a data stream, refused for any other",
    )


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
    users: list[strawberry.ID] = strawberry.field(
        description="The users to invite, by their lok id (the `sub` their token carries)"
    )


@strawberry.input(description="The invitation to put away")
class DismissCallInviteInput:
    id: strawberry.ID
