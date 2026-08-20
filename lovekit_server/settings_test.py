from .settings import *  # noqa
from .settings import AUTHENTIKATE
import logging

# Point the test DB at the Postgres service from tests/integration/docker-compose.yaml
# (a throwaway DB with fsync disabled for speed; flushed/truncated per test).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "testdb",
        "USER": "test",
        "PASSWORD": "test",
        "HOST": "localhost",
        "PORT": "5555",
    }
}

# Point the LiveKit client at the dev-mode livekit-server from the same compose file.
# `livekit-server --dev` ships the well-known devkey/secret keypair, so we hard-code
# it here instead of going through the optional `conf.livekit` block.
LIVEKIT = {
    "API_URL": "http://localhost:7780",
    "API_KEY": "devkey",
    "API_SECRET": "secret",
}

# The static token the test HttpContext authenticates as (see tests/conftest.py).
# Django forces DEBUG=False under the test runner, and authentikate 3.0 refuses static
# tokens when DEBUG is False. These are deliberate test fixtures, so opt in explicitly.
AUTHENTIKATE = {
    **AUTHENTIKATE,
    "allow_static_tokens_in_production": True,
    "static_tokens": {
        "test": {"sub": "1"},
        # A second, distinct identity for ownership/cross-user denial tests. The
        # AuthentikateExtension re-resolves the user from the Bearer token at
        # resolve time, so a different *user* requires a different *token*.
        "othertest": {"sub": "9"},
    },
}

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


# Disable migrations for faster tests
class DisableMigrations:
    """Disable migrations during testing for faster test execution."""

    def __contains__(self, item: str) -> bool:
        """Check if item is in migration modules."""
        return True

    def __getitem__(self, item: str) -> None:
        """Get migration module for item."""
        return None


MIGRATION_MODULES = DisableMigrations()

# Disable logging during tests to reduce noise
logging.disable(logging.CRITICAL)
