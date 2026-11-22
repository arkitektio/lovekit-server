from enum import Enum

import strawberry


@strawberry.enum(description="What a stream carries")
class StreamKind(str, Enum):
    """What a stream carries: pictures, sound or values."""

    VIDEO = "video"
    AUDIO = "audio"
    DATA = "data"


@strawberry.enum(
    description="How a stream is carried from its agent to whoever watches"
)
class Transport(str, Enum):
    """The carrier a connection is for; a client refuses one it does not speak."""

    LIVEKIT = "livekit"


@strawberry.enum(
    description="The semantic kind of an axis, as mikro's coordinate systems name them"
)
class AxisType(str, Enum):
    """The same values as mikro's ``AxisType``, so a stream and stored data name an axis alike."""

    SPACE = "SPACE"
    TIME = "TIME"
    CHANNEL = "CHANNEL"
    COORDINATE = "COORDINATE"
    DISPLACEMENT = "DISPLACEMENT"
    MICROTIME = "MICROTIME"
    SPECTRUM = "SPECTRUM"
    INDEX = "INDEX"
    VALUE = "VALUE"
    CATEGORY = "CATEGORY"
