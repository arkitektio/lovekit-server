"""An agent declaring its streams: the declared set is what it offers, and a restart changes nothing.

An agent is one client, user and organization. Each test declares through the schema and then
asserts the rows, and that a declaration that changes nothing writes nothing.
"""

import threading

import pytest
from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.db.models.signals import post_delete, post_save

from bridge.models import Agent, Stream

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.docker]


DECLARE = """
mutation ($input: DeclareStreamsInput!) {
  declareStreams(input: $input) { id key title kind description agent { id roomName } descriptors }
}
"""

CAMERAS = [
    {"key": "camera", "title": "Main camera"},
    {"key": "overview", "title": "Overview", "description": "The whole stage"},
]


async def _declare(aexecute, streams, context=None):
    res = await aexecute(DECLARE, {"input": {"streams": streams}}, context=context)
    assert not res.errors, res.errors
    return res.data["declareStreams"]


class _Writes:
    """Every save and delete of a stream while it is open: what a hub signal would be sent for."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, int]] = []

    def _saved(self, sender, instance, created, **kwargs) -> None:
        self.seen.append(("created" if created else "updated", instance.id))

    def _deleted(self, sender, instance, **kwargs) -> None:
        self.seen.append(("deleted", instance.id))

    def __enter__(self) -> "_Writes":
        post_save.connect(self._saved, sender=Stream, weak=False)
        post_delete.connect(self._deleted, sender=Stream, weak=False)
        return self

    def __exit__(self, *exc) -> None:
        post_save.disconnect(self._saved, sender=Stream)
        post_delete.disconnect(self._deleted, sender=Stream)


async def test_an_agent_declares_its_streams(aexecute):
    streams = await _declare(aexecute, CAMERAS)

    assert [(s["key"], s["title"], s["kind"]) for s in streams] == [("camera", "Main camera", "VIDEO"), ("overview", "Overview", "VIDEO")]
    assert streams[1]["description"] == "The whole stage"
    # One agent, one room, both streams in it.
    assert streams[0]["agent"] == streams[1]["agent"]
    assert streams[0]["agent"]["roomName"] == f"agent-{streams[0]['agent']['id']}"
    assert streams[0]["descriptors"] == {"@lovekit/stream_kind": "video"}
    assert await Agent.objects.acount() == 1


async def test_a_title_defaults_to_the_key(aexecute):
    [stream] = await _declare(aexecute, [{"key": "microscope", "kind": "AUDIO"}])
    assert (stream["title"], stream["kind"]) == ("microscope", "AUDIO")


async def test_a_restart_finds_the_same_streams(aexecute):
    first = await _declare(aexecute, CAMERAS)
    again = await _declare(aexecute, CAMERAS)
    assert [s["id"] for s in again] == [s["id"] for s in first]


async def test_a_restart_with_the_same_streams_writes_nothing(aexecute):
    await _declare(aexecute, CAMERAS)
    with _Writes() as writes:
        await _declare(aexecute, CAMERAS)
    assert writes.seen == []


async def test_what_changed_is_saved_and_nothing_else(aexecute):
    first = await _declare(aexecute, CAMERAS)
    changed = [{"key": "camera", "title": "Main camera"}, {"key": "overview", "title": "The stage", "description": "The whole stage"}]
    with _Writes() as writes:
        again = await _declare(aexecute, changed)
    assert writes.seen == [("updated", int(first[1]["id"]))]
    assert again[1]["id"] == first[1]["id"] and again[1]["title"] == "The stage"


async def test_a_stream_left_out_is_removed(aexecute):
    first = await _declare(aexecute, CAMERAS)
    with _Writes() as writes:
        again = await _declare(aexecute, [{"key": "camera", "title": "Main camera"}, {"key": "detector"}])
    assert [s["key"] for s in again] == ["camera", "detector"]
    assert ("deleted", int(first[1]["id"])) in writes.seen
    assert not await Stream.objects.filter(id=first[1]["id"]).aexists()


async def test_declaring_nothing_removes_every_stream(aexecute):
    await _declare(aexecute, CAMERAS)
    assert await _declare(aexecute, []) == []
    assert await Stream.objects.acount() == 0
    # The agent stays: it is the same one when it declares again.
    assert await Agent.objects.acount() == 1


async def test_a_key_is_declared_once(aexecute):
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": "camera"}, {"key": "camera"}]}})
    assert res.errors and "camera" in res.errors[0].message
    assert await Stream.objects.acount() == 0


async def test_a_stream_needs_a_key(aexecute):
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": " "}]}})
    assert res.errors


async def test_another_app_is_another_agent(aexecute, second_app_context):
    mine = await _declare(aexecute, CAMERAS)
    theirs = await _declare(aexecute, CAMERAS, context=second_app_context)
    assert mine[0]["agent"]["id"] != theirs[0]["agent"]["id"]
    # Each agent's declaration is its own: the second app's left mine alone.
    assert await Stream.objects.acount() == 4


async def test_another_user_of_the_same_app_is_another_agent(aexecute, other_user_context):
    mine = await _declare(aexecute, CAMERAS)
    theirs = await _declare(aexecute, [{"key": "camera"}], context=other_user_context)
    assert mine[0]["agent"]["id"] != theirs[0]["agent"]["id"]
    assert await Stream.objects.filter(agent_id=mine[0]["agent"]["id"]).acount() == 2


async def test_two_processes_declaring_at_once_make_one_agent(authenticated_context):
    """Two replicas taking the first declaration at the same moment: real threads, each its own connection."""
    from asgiref.sync import async_to_sync

    from lovekit_server.schema import schema

    barrier = threading.Barrier(2)
    errors: list[object] = []

    def declare() -> None:
        try:
            barrier.wait()
            res = async_to_sync(schema.execute)(DECLARE, variable_values={"input": {"streams": CAMERAS}}, context_value=authenticated_context)
            if res.errors:
                errors.extend(res.errors)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=declare) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert await Agent.objects.acount() == 1
    assert await sync_to_async(lambda: sorted(Stream.objects.values_list("key", flat=True)))() == ["camera", "overview"]
