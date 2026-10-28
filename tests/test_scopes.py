"""What an app may do here is what its token's scopes say: every root field asks for one of lovekit's
own (the ``@auth`` directive publishes it, a generated client gathers it), and `lovekit_all` stands
for all of them."""

import pytest
from kante.context import HttpContext, UniversalRequest
from strawberry.http.temporal_response import TemporalResponse

from arkitekt_service.graphql import scope_gaps
from lovekit_server.schema import schema

DECLARE = 'mutation { declareStreams(input: {streams: [{key: "camera"}]}) { id key } }'
STREAMS = "query { streams { id } }"


def _as(token: str) -> HttpContext:
    return HttpContext(request=UniversalRequest(_extensions={}), response=TemporalResponse(), headers={"Authorization": f"Bearer {token}"}, type="http")


def _reason(result) -> str | None:
    return result.errors[0].extensions.get("reason") if result.errors else None


def test_every_root_field_asks_for_a_scope_lovekit_declares():
    assert scope_gaps(schema) == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_an_app_granted_watching_watches_and_streams_nothing(backend_stack):
    assert (await schema.execute(STREAMS, context_value=_as("readertest"))).errors is None
    refused = await schema.execute(DECLARE, context_value=_as("readertest"))
    assert _reason(refused) == "INSUFFICIENT_SCOPE"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_the_all_scope_streams(backend_stack):
    declared = await schema.execute(DECLARE, context_value=_as("test"))
    assert declared.errors is None, declared.errors
