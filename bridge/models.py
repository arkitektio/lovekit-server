from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.conf import settings

from typing import List
from authentikate.models import Client, User


class Agent(models.Model):
    instance_id = models.CharField(max_length=10000, null=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="agents",
        help_text="The user that created this comment",
    )
    
    @property
    def streamlit_room_id(self) -> str:
        """
        Returns the room ID for this agent. All streams created by this agent will use this room ID.
        """
        return f"agent-streams-{self.id}"


class Stream(models.Model):
    agent = models.ForeignKey(
        "Agent",
        on_delete=models.CASCADE,
        related_name="streams",
        help_text="The agent that created this stream",
    )
    title = models.CharField(max_length=1000, help_text="The Title of the Stream")
    token = models.CharField(max_length=4000, help_text="The token of the stream")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "title"], name="Unique stream for agent"
            )
        ]
        
    def streamlit_room_id(self) -> str:
        """
        Returns the room ID for the stream.
        """
        return f"agent-stream-id-{self.id}"


from .signals import * 