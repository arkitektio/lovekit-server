from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.conf import settings

from typing import List
from authentikate.models import Client, User



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
        
    
    

from .signals import * 