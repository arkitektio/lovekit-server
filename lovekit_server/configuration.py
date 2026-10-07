"""Typed, fully-documented configuration schema for the **lovekit** service.

Owned by this service. Values resolve (highest precedence first) from init
kwargs, environment variables (nested via ``__`` — e.g. ``POSTGRES__PASSWORD``),
then the YAML file (``config.yaml`` where the service runs by default; override with
``ARKITEKT_CONFIG_FILE``). Secret fields have **no default**: loading fails fast
with a ``ValidationError`` if they are not supplied via config or environment.
"""

from typing import Optional

from pydantic import BaseModel, Field

from arkitekt_service.server import settings as shared
from arkitekt_service.server.settings import DjangoSettings, PostgresSettings, ServiceSettings
from authentikate.base_models import AuthentikateSettings

class RedisSettings(shared.RedisSettings):
    """Redis connection (channel layer / cache)."""

    channel_prefix: str = Field(default="lovekit", description="Key prefix for the channels_redis channel layer. Must be unique per service: every service on a shared redis used to send under the same prefix, so identically-named groups (e.g. \"files\") delivered one service's events to another's subscribers.")


class LivekitSettings(BaseModel):
    """LiveKit realtime media server credentials (optional block)."""

    api_key: str = Field(description="LiveKit API key.")
    api_secret: str = Field(description="LiveKit API secret. Secret — must be set.")
    api_url: str = Field(description="LiveKit server URL.")


class Settings(ServiceSettings):
    """Top-level, validated configuration for the lovekit service."""

    django: DjangoSettings = Field(description="Core Django settings.")
    postgres: PostgresSettings = Field(description="PostgreSQL connection.")
    redis: RedisSettings = Field(description="Redis connection.")
    authentikate: AuthentikateSettings = Field(description="Token-verification config (authentikate).")
    livekit: Optional[LivekitSettings] = Field(default=None, description="Optional LiveKit media server credentials.")
