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
        channels.pod_channel.broadcast(
            channel_signals.PodSignal(
                create=instance.id,
            )
        )
    else:
        channels.pod_channel.broadcast(
            channel_signals.PodSignal(
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
    channels.pod_channel.broadcast(
        channel_signals.PodSignal(
            delete=instance.id,
        )
    )