import strawberry
from enum import Enum


@strawberry.enum(description="The state of a dask cluster")
class StreamKind(str, Enum):
    """The state of a dask cluster"""
    VIDEO = "video"
    AUDIO = "audio"
    

