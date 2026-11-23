"""Sharing a workflow, in lovekit: nothing here says which workflow made it.

An agent is the identity an app runs as, made the first time it declares its streams and kept across
every workflow after; its streams are what it declares, upserted by key. Neither records a creating
task (no ``created_through``, no history), so ``shareWorkflow`` reports both structures as
``unknown`` and puts nothing in, and ``createdUnder`` lists nothing. Handing out an agent opens its
whole room: that stays a member's decision, by hand (``addToCollaboration``), and
``inCollaboration`` lists what that put in.

The collaboration is lok's, named by a key: a full member shares under a fresh one, and a guest's
token names the same key.
"""

import uuid

import pytest
from arkitekt_service.collaborations.models import Collaboration, CollaborationItem
from kante.context import HttpContext
from strawberry.types import ExecutionResult

from lovekit_server.schema import schema
from tests.support import GuestFactory, data_of, token_context

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.docker,
]

SHARE = """
mutation ($input: ShareWorkflowInput!) {
  shareWorkflow(input: $input) {
    collaboration
    dryRun
    added { identifier object }
    covered
    skipped { identifier object wholeIdentifier whole }
    unknown
  }
}
"""
DECLARE = "mutation ($input: DeclareStreamsInput!) { declareStreams(input: $input) { id key agent { id } } }"
ADD_MANY = "mutation ($input: AddManyToCollaborationInput!) { addManyToCollaboration(input: $input) { key } }"
LISTS = """
query ($agents: AgentFilter, $streams: StreamFilter) {
  agents(filters: $agents) { id }
  streams(filters: $streams) { key }
}
"""


async def _run(ctx: HttpContext, query: str, **variables: object) -> ExecutionResult:
    return await schema.execute(
        query, context_value=ctx, variable_values=variables or None
    )


async def _member(query: str, token: str = "test", **variables: object) -> dict:
    """Run ``query`` as a full member (static ``token``), as a request of its own; its data."""
    result = await _run(token_context(token), query, **variables)
    assert not result.errors, result.errors
    return data_of(result)


async def _declare(token: str, *keys: str) -> str:
    """The agent of ``token``'s app offers exactly these streams; its id."""
    declared = await _member(
        DECLARE, token, input={"streams": [{"key": key} for key in keys]}
    )
    return declared["declareStreams"][0]["agent"]["id"]


def _report(key: str, *, dry_run: bool) -> dict:
    return {
        "collaboration": key,
        "dryRun": dry_run,
        "added": [],
        "covered": 0,
        "skipped": [],
        "unknown": ["@lovekit/agent", "@lovekit/stream"],
    }


async def test_a_workflow_shares_nothing_here_and_says_why(
    authenticated_context: HttpContext, guest: GuestFactory
) -> None:
    await _declare("test", "camera", "overview")
    key = str(uuid.uuid4())
    root = f"root-{uuid.uuid4().hex}"

    tried = await _member(
        SHARE, input={"collaboration": key, "rootTask": root, "dryRun": True}
    )
    assert tried["shareWorkflow"] == _report(key, dry_run=True)
    assert not await Collaboration.objects.filter(key=key).aexists(), (
        "a dry run makes no row of the collaboration here"
    )

    shared = await _member(
        SHARE, input={"collaboration": key, "rootTask": root, "name": "Pilot"}
    )
    assert shared["shareWorkflow"] == _report(key, dry_run=False)
    assert await CollaborationItem.objects.acount() == 0
    seen = await _run(guest({key: []}), LISTS)
    assert not seen.errors, seen.errors
    assert seen.data == {"agents": [], "streams": []}, (
        "no agent, and no room, is handed out by a workflow"
    )


async def test_lists_filter_by_collaboration_and_list_nothing_as_a_workflows(
    authenticated_context: HttpContext,
    second_app_context: HttpContext,
    guest: GuestFactory,
) -> None:
    agent = await _declare("test", "camera", "overview")
    other = await _declare("secondapp", "elsewhere")
    key = str(uuid.uuid4())
    inside = {"inCollaboration": key}

    nothing_yet = await _member(LISTS, agents=inside, streams=inside)
    assert nothing_yet == {"agents": [], "streams": []}

    await _member(
        ADD_MANY,
        input={
            "collaboration": key,
            "objects": [{"identifier": "@lovekit/agent", "object": agent}],
        },
    )
    shared = await _member(LISTS, agents=inside, streams=inside)

    assert shared["agents"] == [{"id": agent}]
    assert sorted(s["key"] for s in shared["streams"]) == ["camera", "overview"], (
        "the agent's streams are part of it, live"
    )
    granted = await _run(guest({key: []}), LISTS)
    assert not granted.errors, granted.errors
    assert granted.data is not None
    assert granted.data["agents"] == [{"id": agent}]
    assert other not in {a["id"] for a in granted.data["agents"]}

    under = {"createdUnder": f"root-{uuid.uuid4().hex}"}
    made = await _member(LISTS, agents=under, streams=under)
    assert made == {"agents": [], "streams": []}, (
        "nothing here says what a workflow made"
    )
    both = await _member(
        LISTS,
        agents={**under, "inCollaboration": key},
        streams={**under, "inCollaboration": key},
    )
    assert both == {"agents": [], "streams": []}


async def test_an_explicit_null_filters_nothing(
    authenticated_context: HttpContext, second_app_context: HttpContext
) -> None:
    agent = await _declare("test", "camera")
    other = await _declare("secondapp", "elsewhere")
    unset = {"inCollaboration": None, "createdUnder": None}

    listed = await _member(LISTS, agents=unset, streams=unset)

    assert {a["id"] for a in listed["agents"]} == {agent, other}
    assert sorted(s["key"] for s in listed["streams"]) == ["camera", "elsewhere"]
