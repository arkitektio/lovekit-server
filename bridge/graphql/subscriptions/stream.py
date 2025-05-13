from typing import AsyncGenerator

import strawberry
import strawberry_django
from kante.types import Info
from bridge import models, scalars, types, channels


@strawberry.type
class StreamEvent:
    create: types.Stream | None = None
    delete: strawberry.ID | None = None
    update: types.Stream    | None = None
    moved: types.Stream | None = None


async def streams(
    self,
    info: Info,
    dataset: strawberry.ID | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """Join and subscribe to message sent to the given rooms."""

    if dataset is None:
        schannels = ["files"]
    else:
        schannels = ["dataset_files_" + str(dataset)]



    async for message in channels.stream_channel.listen(info.context, schannels):
        print("Received message", message)
        if message["type"] == "create":
            roi = await models.File.objects.aget(
                id=message["id"]
            )
            yield StreamEvent(create=roi)

        elif message["type"] == "delete":
            yield StreamEvent(delete=message["id"])

        elif message["type"] == "update":
            roi = await models.File.objects.aget(
                id=message["id"]
            )
            yield StreamEvent(update=roi)

