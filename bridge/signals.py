from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from bridge import models, channel_signals, channels
from typing import Type



@receiver(post_save, sender=models.Stream)
def publish_pod_change(
    sender: Type[models.Stream],
    instance: models.Stream = None,
    created: bool = False,
    **kwargs
) -> None:
    """Sends a message to the pod gateway when a pod is updated"""
    if created:
        channels.stream_channel.broadcast(
            channel_signals.StreamSignal(
                create=instance.id,
            )
        )
    else:
        channels.stream_channel.broadcast(
            channel_signals.StreamSignal(
                update=instance.id,
            )
        )



@receiver(post_delete, sender=models.Stream)
def publish_pod_del(
    sender: Type[models.Stream],
    instance: models.Stream = None,
    created: bool = False,
    **kwargs
) -> None:
    """Sends a message to the pod gateway when a pod is updated"""
    channels.stream_channel.broadcast(
        channel_signals.StreamSignal(
            delete=instance.id,
        )
    )