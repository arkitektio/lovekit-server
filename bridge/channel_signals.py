from pydantic import BaseModel, Field


class StreamSignal(BaseModel):
    """An agent declaring a stream for the first time, changing one, or leaving one out."""

    create: int | None = Field(None, description="The stream that was declared for the first time.")
    update: int | None = Field(None, description="The stream whose title, kind or description changed.")
    delete: int | None = Field(None, description="The stream its agent no longer declares.")


class CallInviteSignal(BaseModel):
    """An invitation to a call arriving for a user, or going away again."""

    create: int | None = Field(None, description="The invite that was created.")
    delete: int | None = Field(None, description="The invite that was dismissed, answered, or whose call ended.")


class CallSignal(BaseModel):
    """A call starting in an organization, or changing what it is about."""

    create: int | None = Field(None, description="The call that was started.")
    update: int | None = Field(None, description="The call that turned to something else to be about.")
