import asyncio
import contextlib
import os
import time

import psycopg
import pytest
import pytest_asyncio
from authentikate.models import Client, Membership, Organization, User
from django.contrib.contenttypes.management import create_contenttypes
from django.db.models.signals import post_migrate
from dokker import testing
from kante.context import HttpContext, UniversalRequest, WsContext
from strawberry.http.temporal_response import TemporalResponse


@pytest.fixture(scope="session")
def backend_stack():
    docker_compose_path = os.path.join(
        os.path.dirname(__file__), "integration", "docker-compose.yaml"
    )

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

    post_migrate.disconnect(
        dispatch_uid="django.contrib.auth.management.create_permissions"
    )
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
    org, _ = Organization.objects.get_or_create(identifier=f"static_issuer#{org_slug}")
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
    return _make_context(
        token="test", sub="1", username="static_issuer_1", org_slug="static_org"
    )


@pytest.fixture(scope="function")
def other_user_context(db, backend_stack) -> HttpContext:
    """A second, distinct user — for ownership/cross-user denial tests.

    Uses the "othertest" static token (sub 9) so the AuthentikateExtension
    actually authenticates it as a separate user.
    """
    return _make_context(
        token="othertest", sub="9", username="static_issuer_9", org_slug="static_org"
    )


@pytest.fixture(scope="function")
def stranger_context(db, backend_stack) -> HttpContext:
    """The second user in ANOTHER organization ("stranger"), for tenant scoping tests."""
    return _make_context(
        token="stranger", sub="9", username="static_issuer_9", org_slug="another_org"
    )


@pytest.fixture(scope="function")
def second_app_context(db, backend_stack) -> HttpContext:
    """The first user running a second app ("secondapp"): another client, so another agent."""
    return _make_context(
        token="secondapp", sub="1", username="static_issuer_1", org_slug="static_org"
    )


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


# ---------------------------------------------------------------------------
# Subscriptions, in-process: a websocket context on the in-memory channel layer.
# ---------------------------------------------------------------------------


class Subscriber:
    """Drives one subscription from a single task, collecting what it yields.

    The AuthentikateExtension sets and resets context variables around the operation,
    which must happen in the same task; cancelling the task closes the subscription the
    way a client disconnect would.
    """

    def __init__(
        self, context: WsContext, query: str, variables: dict[str, object]
    ) -> None:
        self.context = context
        self.query = query
        self.variables = variables
        self.events: asyncio.Queue = asyncio.Queue()
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        from lovekit_server.schema import schema

        subscription = await schema.subscribe(
            self.query, variable_values=self.variables, context_value=self.context
        )
        if hasattr(subscription, "errors"):
            self.events.put_nowait(subscription)
            return
        async for result in subscription:
            self.events.put_nowait(result)

    async def next(self, timeout: float = 5) -> dict:
        result = await asyncio.wait_for(self.events.get(), timeout)
        assert not result.errors, result.errors
        return result.data

    async def nothing(self, timeout: float = 0.5) -> bool:
        """True when nothing more arrives within ``timeout``."""
        try:
            await asyncio.wait_for(self.events.get(), timeout)
        except TimeoutError:
            return True
        return False

    async def close(self) -> None:
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


@pytest_asyncio.fixture
async def subscribe(db, backend_stack):
    """Start a subscription as a static token, once it listens on ``group``; closed after the test.

    One ``ChannelsConsumer`` per subscriber, bound to the in-memory layer, with a pump that
    feeds the layer's messages into it (what the websocket handler does).
    """
    from channels.layers import get_channel_layer
    from strawberry.channels import ChannelsConsumer

    layer = get_channel_layer()
    # The in-memory layer is a process-wide singleton; drop what earlier tests left.
    await layer.flush()
    pumps: list[asyncio.Task] = []
    subscribers: list[Subscriber] = []

    async def _start(
        query: str, variables: dict[str, object], group: str, token: str = "test"
    ) -> Subscriber:
        consumer = ChannelsConsumer()
        consumer.channel_layer = layer
        consumer.channel_name = await layer.new_channel()

        async def pump() -> None:
            while True:
                await consumer.dispatch(await layer.receive(consumer.channel_name))

        pumps.append(asyncio.create_task(pump()))
        context = WsContext(
            request=UniversalRequest(_extensions={"token": token}),
            response=TemporalResponse(),
            connection_params={"token": token},
            consumer=consumer,
        )
        subscriber = Subscriber(context, query, variables)
        subscribers.append(subscriber)
        for _ in range(500):
            if subscriber.task.done():
                subscriber.task.result()
                pytest.fail(
                    f"subscription ended before listening: {subscriber.events.get_nowait()}"
                )
            if consumer.channel_name in layer.groups.get(group, {}):
                return subscriber
            await asyncio.sleep(0.01)
        pytest.fail(f"subscription never joined {group}")

    yield _start

    for subscriber in subscribers:
        await subscriber.close()
    for task in pumps:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
