from pydantic import BaseModel, Field


class StreamSignal(BaseModel):
    """An agent declaring a stream for the first time, changing one, leaving one out, or
    starting and stopping to publish it."""

    create: int | None = Field(None, description="The stream that was declared for the first time.")
    update: int | None = Field(None, description="The stream whose title, kind, description or format changed.")
    delete: int | None = Field(None, description="The stream its agent no longer declares.")
    live: int | None = Field(None, description="The stream its agent started publishing (LiveKit's webhook).")
    offline: int | None = Field(None, description="The stream its agent stopped publishing (LiveKit's webhook).")


class CallInviteSignal(BaseModel):
    """An invitation to a call arriving for a user, or going away again."""

    create: int | None = Field(None, description="The invite that was created.")
    delete: int | None = Field(None, description="The invite that was dismissed, answered, or whose call ended.")


class CallSignal(BaseModel):
    """A call starting in an organization, changing what it is about, ending, or coming back."""

    create: int | None = Field(None, description="The call that was started.")
    update: int | None = Field(None, description="The call that turned to something else to be about.")
    ended: int | None = Field(None, description="The call whose LiveKit room closed: everyone left and the room timed out.")
    resumed: int | None = Field(None, description="The call whose room came up again after it had ended.")


class CallParticipantSignal(BaseModel):
    """Someone joining or leaving one call's room, as LiveKit's webhook reports it."""

    call: int = Field(description="The call whose room this happened in.")
    identity: str = Field(description="The participant's LiveKit identity.")
    name: str = Field("", description="What the participant is called.")
    joined_at: int = Field(0, description="When the participant joined, in seconds since the epoch.")
    left: bool = Field(False, description="True when the participant left, false when they joined.")
