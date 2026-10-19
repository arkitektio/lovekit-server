import strawberry
from enum import Enum


@strawberry.enum(description="What a stream carries")
class StreamKind(str, Enum):
    """What a stream carries: pictures or sound."""

    VIDEO = "video"
    AUDIO = "audio"
