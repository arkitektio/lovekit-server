from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.conf import settings

from typing import List
from authentikate.models import Client, User, Organization



class Broadcast(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time this broadcast was created")
    
       
    @property
    def streamlit_room_id(self) -> str:
        """
        Returns the room ID for this agent. All streams created by this agent will use this room ID.
        """
        return f"broadcast-{self.id}"
        
class SoloBroadcast(Broadcast):
    title = models.CharField(max_length=1000, help_text="The Title of the Broadcast")

    streamer = models.ForeignKey(
        "Streamer",
        on_delete=models.CASCADE,
        related_name="solo_broadcasts",
        help_text="The agent that created this private broadcast",
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["title", "streamer"], name="Unique broadcast title for solo broadcast"
            )
        ]
    
    
class CollaborativeBroadcast(Broadcast):
    title = models.CharField(max_length=1000, help_text="The Title of the Broadcast")
    streamers = models.ManyToManyField(
        "Streamer",
        related_name="collaborative_broadcasts",
        help_text="Users that can collaborate on this broadcast",
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["title"], name="Unique broadcast title for collaborative broadcast"
            )
        ]
    



class Streamer(models.Model):
    instance_id = models.CharField(max_length=10000, null=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="streamers",
        help_text="The user that created this comment",
    )
    
    @property
    def streamlit_participant_id(self) -> str:
        """
        Returns the room ID for this agent. All streams created by this agent will use this room ID.
        """
        return f"streamer-{self.id}"
 



class Stream(models.Model):
    streamer = models.ForeignKey(
        "Streamer",
        on_delete=models.CASCADE,
        related_name="streams",
        help_text="The agent that created this stream",
    )
    broadcast = models.ForeignKey(
        "Broadcast",
        on_delete=models.CASCADE,
        related_name="streams",
        null=True,
        blank=True,
        help_text="The broadcast this stream belongs to, if any.",
    )
    kind = models.CharField(
        max_length=50,
        help_text="The type of stream",
    )
    
    title = models.CharField(max_length=1000, help_text="The Title of the Stream")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["streamer", "title"], name="Unique stream for agent"
            )
        ]
        
    
    



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


from .signals import * 