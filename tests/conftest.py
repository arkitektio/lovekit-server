import os
import time

import psycopg
import pytest
import pytest_asyncio
from asgiref.sync import sync_to_async

from authentikate.models import Client, Organization, User, Membership
from django.contrib.contenttypes.management import create_contenttypes
from django.db.models.signals import post_migrate
from kante.context import HttpContext, UniversalRequest
from strawberry.http.temporal_response import TemporalResponse
from dokker import testing


@pytest.fixture(scope="session")
def backend_stack():
    docker_compose_path = os.path.join(os.path.dirname(__file__), "integration", "docker-compose.yaml")

    with testing(docker_compose_path) as e:
        e.inspect()

        e.down()

        e.up()

        # livekit-server is ready once its HTTP endpoint answers on /. Gate on it
        # before yielding so the first create_room() doesn't race the boot.
        e.add_health_check(
            url="http://localhost:7780/",
            service="livekit",
            max_retries=30,
            timeout=1,  # ~30s total, matching the postgres deadline below
        )
        e.check_health()

        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg.connect(
                    dbname="testdb",
                    user="test",
                    password="test",
                    host="localhost",
                    port=5555,
                    connect_timeout=1,
                ) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)

        yield


@pytest.fixture(scope="session")
def django_db_modify_db_settings(backend_stack):
    """Start the backend services before pytest-django configures the test DB."""
    yield


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    # Every transaction=True test teardown flushes the DB and re-fires
    # post_migrate, which rebuilds all contenttypes and permissions from the
    # model registry (~1s per test). The rows never change between tests, so
    # snapshot them once and swap the rebuild for a bulk re-insert with the
    # original pks.
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    with django_db_blocker.unblock():
        contenttypes = list(ContentType.objects.all())
        permissions = list(Permission.objects.all())

    post_migrate.disconnect(dispatch_uid="django.contrib.auth.management.create_permissions")
    post_migrate.disconnect(create_contenttypes)

    def restore_contenttypes_and_permissions(sender, **kwargs):
        # post_migrate fires once per app config on flush; restore once.
        if getattr(sender, "label", None) != "contenttypes":
            return
        ContentType.objects.bulk_create(contenttypes, ignore_conflicts=True)
        Permission.objects.bulk_create(permissions, ignore_conflicts=True)

    post_migrate.connect(
        restore_contenttypes_and_permissions,
        dispatch_uid="tests.restore_contenttypes_and_permissions",
    )
    yield

    # The async tests run sync ORM code in asgiref's executor threads, whose
    # connections outlive the tests and block dropping the test database
    # ("database is being accessed by other users"). Kill them before
    # pytest-django's teardown drops the database.
    from django.db import connections

    with django_db_blocker.unblock():
        with connections["default"].cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        connections.close_all()


def _make_context(token: str, sub: str, username: str, org_slug: str) -> HttpContext:
    """Build a kante HttpContext that resolves to the given static token identity."""
    user, _ = User.objects.get_or_create(
        sub=sub, iss="static_issuer", defaults={"username": username}
    )
    client, _ = Client.objects.get_or_create(client_id="oinsoins")
    org, _ = Organization.objects.get_or_create(slug=org_slug)
    membership, _ = Membership.objects.get_or_create(user=user, organization=org)

    request = UniversalRequest(
        _extensions={"token": token},
        _client=client,  # type: ignore
        _user=user,  # type: ignore
        _organization=org,  # type: ignore
    )
    request.set_membership(membership)  # type: ignore

    return HttpContext(
        request=request,
        response=TemporalResponse(),
        headers={"Authorization": f"Bearer {token}"},
        type="http",
    )


@pytest.fixture(scope="function")
def authenticated_context(db, backend_stack) -> HttpContext:
    # Match the identity the static "test" token resolves to (see settings_test
    # AUTHENTIKATE static_tokens), so the user/client on this context is the same
    # one the schema's AuthentikateExtension authenticates as at resolve time.
    return _make_context(token="test", sub="1", username="static_issuer_1", org_slug="static_org")


@pytest.fixture(scope="function")
def other_user_context(db, backend_stack) -> HttpContext:
    """A second, distinct user — for ownership/cross-user denial tests.

    Uses the "othertest" static token (sub 9) so the AuthentikateExtension
    actually authenticates it as a separate Streamer-owning user.
    """
    return _make_context(token="othertest", sub="9", username="static_issuer_9", org_slug="static_org")


# ---------------------------------------------------------------------------
# Mutation-test helpers: execute against the schema + build prerequisite rows.
# ---------------------------------------------------------------------------


@pytest.fixture
def aexecute(authenticated_context):
    """Run a GraphQL document against the schema, defaulting to the authed context."""
    from lovekit_server.schema import schema

    async def _run(query, variables=None, context=None):
        return await schema.execute(
            query,
            variable_values=variables or {},
            context_value=context or authenticated_context,
        )

    return _run


@pytest_asyncio.fixture
async def livekit_client(backend_stack):
    """The LiveKit API client (same one the mutations use), for asserting room state.

    Async fixture so the aiohttp-backed client is created and closed on the same
    event loop the test body runs in.
    """
    from bridge.api import get_api

    client = get_api()
    yield client
    await client.aclose()


@pytest.fixture
def make_streamer(authenticated_context):
    """Factory: create a Streamer row for a given context's user/client."""
    from bridge.models import Streamer

    @sync_to_async
    def _make(context=None):
        ctx = context or authenticated_context
        streamer, _ = Streamer.objects.get_or_create(
            user=ctx.request.user,
            client=ctx.request.client,
        )
        return streamer

    return _make


@pytest.fixture
def make_solo_broadcast(authenticated_context, make_streamer):
    """Factory: create a SoloBroadcast row (no LiveKit room — DB only)."""
    from bridge.models import SoloBroadcast, Streamer

    @sync_to_async
    def _make(context=None, title="Untitled"):
        ctx = context or authenticated_context
        streamer, _ = Streamer.objects.get_or_create(
            user=ctx.request.user,
            client=ctx.request.client,
        )
        broadcast, _ = SoloBroadcast.objects.get_or_create(streamer=streamer, title=title)
        return broadcast

    return _make
