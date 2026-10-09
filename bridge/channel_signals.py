from pydantic import BaseModel, Field


class StreamSignal(BaseModel):
    """A model representing a stream update event."""
    create: int | None = Field(None, description="The stream that was created.")
    update: int | None = Field(None, description="The stream that was updated.")
    delete: int | None = Field(None, description="The stream that was deleted.")


class CallInviteSignal(BaseModel):
    """An invitation to a call arriving for a user, or going away again."""

    create: int | None = Field(None, description="The invite that was created.")
    delete: int | None = Field(None, description="The invite that was dismissed, answered, or whose call ended.")
