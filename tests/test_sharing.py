"""A guest of the organization, granted a collaboration and nothing else: what they see, and what they may watch.

Their token lists their collaborations by service instance (`collabs`, instance "1" in the test settings),
with the roles they hold in each; the guest token is minted per test. A full member ("test")
puts an agent or a stream in a collaboration; an agent's streams are part of it. Watching is the
one thing a guest may ask for, of an agent they were granted: a watch token opens its whole room.
"""

from collections.abc import Callable, Iterator
from typing import TypeAlias

import pytest
from arkitekt_service.collaborations import items as collaboration_items
from arkitekt_service.collaborations.models import Collaboration
from asgiref.sync import sync_to_async
from authentikate import settings as authentikate_settings
from django.conf import settings as django_settings
from django.db.models import Model
from kante.context import HttpContext, UniversalRequest
from livekit.api import TokenVerifier
from livekit.api.access_token import Claims
from pytest_django.fixtures import SettingsWrapper
from strawberry.http.temporal_response import TemporalResponse
from strawberry.types import ExecutionResult

from bridge import models
from lovekit_server.schema import schema
from tests.support import data_of

DECLARE = """
mutation ($input: DeclareStreamsInput!) {
  declareStreams(input: $input) { id key agent { id roomName } }
}
"""
SEEN = "{ agents { id name streams { id key } } streams { id key agent { id } } }"
STREAM = "query ($id: ID!) { stream(id: $id) { id key } }"
AGENT = "query ($id: ID!) { agent(id: $id) { id name streams { key } } }"
WATCH_STREAM = "mutation ($input: WatchStreamInput!) { watchStream(input: $input) { transport credential } }"
WATCH_AGENT = "mutation ($input: WatchAgentInput!) { watchAgent(input: $input) { transport credential } }"
ENSURE_CALL = "mutation ($input: EnsureCallInput!) { ensureCall(input: $input) { id } }"


def _context(token: str) -> HttpContext:
    return HttpContext(
        request=UniversalRequest(_extensions={}),
        response=TemporalResponse(),
        headers={"Authorization": f"Bearer {token}"},
        type="http",
    )


#: The ``guest`` fixture: a context for a guest granted these collaborations (or ids), with these roles.
Guest: TypeAlias = Callable[[dict[Collaboration | str, list[str]]], HttpContext]


@pytest.fixture
def guest(
    db: None, authenticated_context: HttpContext, settings: SettingsWrapper
) -> Iterator[Guest]:
    """``guest({collaboration: roles})``: a context presenting a guest's token granted those collaborations on instance "1"."""

    def mint(collaborations: dict[Collaboration | str, list[str]]) -> HttpContext:
        granted = {
            str(
                collaboration.pk
                if isinstance(collaboration, Collaboration)
                else collaboration
            ): roles
            for collaboration, roles in collaborations.items()
        }
        settings.AUTHENTIKATE = {
            **settings.AUTHENTIKATE,
            "static_tokens": {
                **settings.AUTHENTIKATE["static_tokens"],
                "guest": {
                    "sub": "20",
                    "roles": [],
                    "collabs": {"1": granted},
                    "scope": "openid lovekit_all",
                },
            },
        }
        authentikate_settings.cached_settings = None
        return _context("guest")

    yield mint
    authentikate_settings.cached_settings = None


async def _run(ctx: HttpContext, query: str, **variables: object) -> ExecutionResult:
    return await schema.execute(
        query, context_value=ctx, variable_values=variables or None
    )


async def _declare(ctx: HttpContext, *keys: str) -> dict[str, dict]:
    """The caller's agent offers exactly these streams; each by key, with its agent."""
    res = await _run(ctx, DECLARE, input={"streams": [{"key": key} for key in keys]})
    assert not res.errors, res.errors
    assert res.data is not None
    return {stream["key"]: stream for stream in res.data["declareStreams"]}


async def _collaboration(ctx: HttpContext, *objects: Model) -> Collaboration:
    """A collaboration of the organization holding ``objects``, as a full member puts them in."""

    def make() -> Collaboration:
        collaboration = Collaboration.objects.create(
            organization=ctx.request.organization, name="Shared"
        )
        for obj in objects:
            collaboration_items.add(collaboration, obj)
        return collaboration

    return await sync_to_async(make)()


async def _agent(stream: dict) -> models.Agent:
    return await models.Agent.objects.aget(id=stream["agent"]["id"])


def _claims(token: str) -> Claims:
    return TokenVerifier(
        django_settings.LIVEKIT["API_KEY"], django_settings.LIVEKIT["API_SECRET"]
    ).verify(token)


def _refused(result: ExecutionResult, reason: str) -> None:
    assert result.errors, "it was let through"
    assert result.errors[0].extensions.get("reason") == reason, result.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_guest_sees_the_agent_in_their_collaboration_and_every_stream_it_offers(
    authenticated_context: HttpContext, second_app_context: HttpContext, guest: Guest
) -> None:
    shared = await _declare(authenticated_context, "camera", "overview")
    other = await _declare(second_app_context, "elsewhere")
    agent = await _agent(shared["camera"])
    ctx = guest({await _collaboration(authenticated_context, agent): []})

    seen = await _run(ctx, SEEN)
    assert not seen.errors, seen.errors
    assert seen.data is not None
    assert [a["id"] for a in seen.data["agents"]] == [str(agent.pk)]
    assert sorted(s["key"] for s in seen.data["agents"][0]["streams"]) == [
        "camera",
        "overview",
    ]
    assert sorted(s["key"] for s in seen.data["streams"]) == ["camera", "overview"]
    assert (
        data_of(await _run(ctx, STREAM, id=shared["overview"]["id"]))["stream"]["key"]
        == "overview"
    )
    assert (await _run(ctx, STREAM, id=other["elsewhere"]["id"])).errors
    assert (await _run(ctx, AGENT, id=other["elsewhere"]["agent"]["id"])).errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_stream_the_agent_declares_later_is_shared_with_it(
    authenticated_context: HttpContext, guest: Guest
) -> None:
    first = await _declare(authenticated_context, "camera")
    ctx = guest(
        {await _collaboration(authenticated_context, await _agent(first["camera"])): []}
    )
    await _declare(authenticated_context, "camera", "detector")

    seen = await _run(ctx, AGENT, id=first["camera"]["agent"]["id"])
    assert not seen.errors, seen.errors
    assert seen.data is not None
    assert sorted(s["key"] for s in seen.data["agent"]["streams"]) == [
        "camera",
        "detector",
    ]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_stream_is_shared_with_its_agent_never_alone(
    authenticated_context: HttpContext,
) -> None:
    """A stream is part of its agent: it is put in a collaboration with the agent, whose room it is heard in."""
    streams = await _declare(authenticated_context, "camera", "microphone")
    camera = await models.Stream.objects.aget(id=streams["camera"]["id"])
    with pytest.raises(collaboration_items.SharedWithItsWhole):
        await _collaboration(authenticated_context, camera)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_guest_watches_a_shared_agent_without_publishing(
    authenticated_context: HttpContext, guest: Guest
) -> None:
    streams = await _declare(authenticated_context, "camera")
    camera = streams["camera"]
    ctx = guest({await _collaboration(authenticated_context, await _agent(camera)): []})

    watched = await _run(ctx, WATCH_STREAM, input={"stream": camera["id"]})
    assert not watched.errors, watched.errors
    assert watched.data is not None
    claims = _claims(watched.data["watchStream"]["credential"])
    assert claims.video.room == camera["agent"]["roomName"]
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish is False
    assert claims.video.can_publish_data is False

    whole = await _run(ctx, WATCH_AGENT, input={"agent": camera["agent"]["id"]})
    assert not whole.errors, whole.errors
    assert whole.data is not None
    assert (
        _claims(whole.data["watchAgent"]["credential"]).video.room
        == camera["agent"]["roomName"]
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_guest_watches_no_agent_they_were_not_granted(
    authenticated_context: HttpContext, second_app_context: HttpContext, guest: Guest
) -> None:
    streams = await _declare(authenticated_context, "camera", "microphone")
    other = await _declare(second_app_context, "elsewhere")
    # Granted the one agent, and nothing of the other.
    ctx = guest(
        {
            await _collaboration(
                authenticated_context, await _agent(streams["camera"])
            ): []
        }
    )

    _refused(
        await _run(ctx, WATCH_STREAM, input={"stream": other["elsewhere"]["id"]}),
        "SHARE_INSUFFICIENT",
    )
    _refused(
        await _run(
            ctx, WATCH_AGENT, input={"agent": other["elsewhere"]["agent"]["id"]}
        ),
        "SHARE_INSUFFICIENT",
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_guest_publishes_nothing_joins_no_call_and_hears_nothing(
    authenticated_context: HttpContext, guest: Guest
) -> None:
    streams = await _declare(authenticated_context, "camera")
    call = await _run(
        authenticated_context,
        ENSURE_CALL,
        input={"about": [{"identifier": "@mikro/image", "object": 42}]},
    )
    assert not call.errors, call.errors
    assert call.data is not None
    call_id = call.data["ensureCall"]["id"]
    collaboration = await _collaboration(
        authenticated_context, await _agent(streams["camera"])
    )
    ctx = guest({collaboration: ["admin", "editor"]})

    for document, variables in [
        (DECLARE, {"input": {"streams": [{"key": "mine"}]}}),
        ("mutation { publisherConnection { credential } }", {}),
        (
            ENSURE_CALL,
            {"input": {"about": [{"identifier": "@mikro/image", "object": 42}]}},
        ),
        (
            "mutation ($input: JoinCallInput!) { joinCall(input: $input) { credential } }",
            {"input": {"call": call_id}},
        ),
        (
            "mutation ($input: InviteToCallInput!) { inviteToCall(input: $input) { id } }",
            {"input": {"call": call_id, "users": ["1"]}},
        ),
        (
            "mutation ($input: CollaborationObjectInput!) { addToCollaboration(input: $input) { id } }",
            {
                "input": {
                    "collaboration": str(collaboration.pk),
                    "identifier": "@lovekit/agent",
                    "object": streams["camera"]["agent"]["id"],
                }
            },
        ),
    ]:
        _refused(await _run(ctx, document, **variables), "SCOPED_READ_ONLY")

    subscribed = await schema.subscribe(
        "subscription { streams { __typename } }", context_value=ctx
    )
    _refused(await anext(subscribed), "SCOPED_READ_ONLY")
    await subscribed.aclose()

    # A call is in no collaboration.
    calls = await _run(ctx, "{ calls { id } myCallInvites { id } }")
    assert not calls.errors, calls.errors
    assert calls.data is not None
    assert calls.data == {"calls": [], "myCallInvites": []}
    assert (
        await _run(ctx, "query ($id: ID!) { call(id: $id) { id } }", id=call_id)
    ).errors
    assert await models.Agent.objects.acount() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_member_shares_an_agent_and_the_guest_sees_only_that_collaboration(
    authenticated_context: HttpContext, guest: Guest
) -> None:
    streams = await _declare(authenticated_context, "camera")
    created = await _run(
        authenticated_context,
        'mutation { createCollaboration(input: { name: "Microscope" }) { id } }',
    )
    assert not created.errors, created.errors
    assert created.data is not None
    collaboration = created.data["createCollaboration"]["id"]
    added = await _run(
        authenticated_context,
        "mutation ($input: CollaborationObjectInput!) { addToCollaboration(input: $input) { id items { identifier objectId brought } } }",
        input={
            "collaboration": collaboration,
            "identifier": "@lovekit/agent",
            "object": streams["camera"]["agent"]["id"],
        },
    )
    assert not added.errors, added.errors
    assert added.data is not None
    assert added.data["addToCollaboration"]["items"] == [
        {
            "identifier": "@lovekit/agent",
            "objectId": streams["camera"]["agent"]["id"],
            "brought": False,
        }
    ]
    await _collaboration(authenticated_context)  # another, not granted
    ctx = guest({collaboration: []})

    listed = await _run(ctx, "{ collaborations { id name } streams { key } }")
    assert not listed.errors, listed.errors
    assert listed.data is not None
    assert listed.data == {
        "collaborations": [{"id": collaboration, "name": "Microscope"}],
        "streams": [{"key": "camera"}],
    }


def test_the_schema_says_what_each_type_is_and_what_a_guest_may_watch() -> None:
    sdl = str(schema)
    assert '@identified(by: "@lovekit/stream")' in next(
        line for line in sdl.splitlines() if line.startswith("type Stream ")
    )
    watch = next(
        line.strip()
        for line in sdl.splitlines()
        if line.strip().startswith("watchStream(")
    )
    assert watch.endswith(
        '@auth(required_scopes: ["lovekit_watch"], allow_scoped: true)'
    ), watch
