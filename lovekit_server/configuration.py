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
from arkitekt_service.server.settings import DjangoSettings, InstanceSettings, PostgresSettings, ServiceSettings
from authentikate.base_models import AuthentikateSettings

class RedisSettings(shared.RedisSettings):
    """Redis connection (channel layer / cache)."""

    channel_prefix: str = Field(default="lovekit", description="Key prefix for the channels_redis channel layer. Must be unique per service: every service on a shared redis used to send under the same prefix, so identically-named groups (e.g. \"files\") delivered one service's events to another's subscribers.")


class LivekitSettings(BaseModel):
    """LiveKit realtime media server credentials (optional block)."""

    api_key: str = Field(description="LiveKit API key.")
    api_secret: str = Field(description="LiveKit API secret. Secret — must be set.")
    api_url: str = Field(description="LiveKit server URL.")


class RekuestHookSettings(BaseModel):
    """How this process reaches the hub's rekuest as a service (``rekuest_service``): where it sends its signals."""

    rekuest_url: str = Field(default="http://rekuest:80/rekuest", description="rekuest's base URL on the internal network.")
    service: str = Field(default="lovekit", description="The name rekuest knows this process by: its `rekuest.services[].name` (signals are sent as it).")
    max_skew: int = Field(default=30, description="Clock skew (seconds) tolerated on a signed request; tokens themselves live 60 s.")


class Settings(ServiceSettings):
    """Top-level, validated configuration for the lovekit service."""

    django: DjangoSettings = Field(description="Core Django settings.")
    postgres: PostgresSettings = Field(description="PostgreSQL connection.")
    redis: RedisSettings = Field(description="Redis connection.")
    authentikate: AuthentikateSettings = Field(description="Token-verification config (authentikate).")
    livekit: Optional[LivekitSettings] = Field(default=None, description="Optional LiveKit media server credentials.")
    rekuest_hook: Optional[RekuestHookSettings] = Field(default=None, description="Announce streams to the hub's rekuest (signals its triggers can fire on). Without it nothing is announced.")
    instance: Optional[InstanceSettings] = Field(default=None, description="This instance's key and the hub trust bundle (signed requests to and from rekuest, no shared secrets).")
