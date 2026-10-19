from arkitekt_service.service.described import Described
from authentikate.models import Client, Organization, User
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from bridge import enums



class Agent(models.Model):
    """An app instance that owns live streams: one per client, user and organization.

    The same key rekuest gives its agents (``facade_agent``): whatever runs as that client,
    for that user, in that organization, is this agent, and a restarted process is the same
    agent again. All of its streams are tracks in one LiveKit room (``room_name``), which only
    the agent publishes into and everyone in its organization may watch.
    """

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="lovekit_agents", help_text="The client (app instance) this agent runs as")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lovekit_agents", help_text="The user this agent runs for")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="lovekit_agents", help_text="The organization whose members may watch this agent's streams")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this agent first declared its streams")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["client", "user", "organization"], name="one_agent_per_client_user_org"),
        ]

    @property
    def room_name(self) -> str:
        """The LiveKit room every stream of this agent is a track in."""
        return f"agent-{self.id}"

    @property
    def publisher_identity(self) -> str:
        """The one identity the agent publishes as: a newer connection replaces an older one."""
        return f"agent-{self.id}"


class Stream(Described):
    """One live source an agent declared: a camera, a detector, a microphone.

    Declared by the agent on every start (``declareStreams``), under a ``key`` of its own
    choosing, so the same source is the same stream (and the same id) across restarts. The key
    is also the name of the LiveKit track the agent publishes it as. Whether it is live is
    LiveKit's answer (the agent publishes a track of that name), not a column here.
    """

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="streams", help_text="The agent that declared this stream")
    key = models.CharField(max_length=200, help_text="The agent's name for this stream, stable across restarts; the name of its LiveKit track")
    title = models.CharField(max_length=1000, help_text="What the stream is called")
    kind = models.CharField(max_length=50, choices=[(kind.value, kind.name) for kind in enums.StreamKind], help_text="Whether this is video or audio")
    description = models.TextField(null=True, blank=True, help_text="What the stream shows")
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the agent first declared this stream")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agent", "key"], name="one_stream_per_agent_key"),
        ]
        indexes = [GinIndex(fields=["stored_descriptors"], name="bridge_stream_desc_gin", opclasses=["jsonb_path_ops"])]

    def __str__(self) -> str:
        return f"{self.title} [{self.key}]"


class Structure(models.Model):
    """A reference to an object on another service, the thing a call is about.

    The same contract as alpaka's rooms: ``identifier`` names the model
    (``@mikro/image``), ``object`` is its id on that service.
    """

    identifier = models.CharField(
        max_length=1000,
        help_text="The identifier of the object. Consult the documentation for the format",
    )
    object = models.PositiveIntegerField(help_text="The object id of the object, on its associated service")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["identifier", "object"], name="Unique structure per identifier and object")
        ]


class Call(models.Model):
    """A multi-party LiveKit room about some structures.

    One call is one LiveKit room (``livekit_room_name``). Everyone in the
    call's organization may join; whether it is live is LiveKit's answer
    (the room exists while someone is in it), not a column here.
    """

    title = models.CharField(max_length=1000, help_text="The title of the call")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="calls",
        help_text="The organization this call belongs to",
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_calls",
        help_text="The user that started this call",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this call was started")
    about = models.ManyToManyField(
        Structure,
        related_name="calls",
        blank=True,
        help_text="The structures this call is about",
    )

    @property
    def livekit_room_name(self) -> str:
        """The LiveKit room every participant of this call joins."""
        return f"call-{self.id}"



class CallInvite(models.Model):
    """Someone asking someone else into a call: the invitation their app rings with.

    An invite is pending until the invitee dismisses it or joins the call
    (from any device), and moot once the call's room is gone. Nothing here
    reaches a phone: it is delivered to the apps the invitee has open, through
    the `callInvites` subscription.
    """

    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="invites")
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_call_invites")
    invitee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="call_invites")
    created_at = models.DateTimeField(auto_now_add=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
