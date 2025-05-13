from pydantic import BaseModel, Field


class StreamSignal(BaseModel):
    """A model representing a stream update event."""
    create: int | None = Field(None, description="The stream that was created.")
    update: int | None = Field(None, description="The stream that was updated.")
    delete: int | None = Field(None, description="The stream that was deleted.")