from kante.types import Info
from bridge import models, types


async def aget_backend_for_info(info: Info, instance_id: str) -> models.Backend:
    """Get the backend for the given info object and instance id"""

    backend, _ = await models.Backend.objects.aget_or_create(
        user=info.context.request.user,
        instance_id=instance_id,
        client=info.context.request.app,
    )

    return backend


def get_backend_for_info(info: Info, instance_id: str) -> models.Backend:
    """Get the backend for the given info object and instance id"""

    backend, _ = models.Backend.objects.aget_or_create(
        user=info.context.request.user,
        instance_id=instance_id,
        client=info.context.request.app,
    )

    return backend
