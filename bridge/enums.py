import strawberry
from enum import Enum


@strawberry.enum(description="The state of a dask cluster")
class PodStatus(str, Enum):
    """The state of a dask cluster"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKOWN = "UNKOWN"


