import hashlib
import json
import logging
from typing import Any, Dict, List, Tuple

import strawberry
import strawberry_django
from kante.types import Info
from bridge import types, models, inputs

logger = logging.getLogger(__name__)
from django.contrib.auth import get_user_model
from livekit import api
from livekit.protocol.room import ListRoomsRequest
from django.conf import settings



async def create_video_stream(info: Info, input: inputs.CreateStreamInput) -> types.Stream:


    agent, _ = await models.Agent.objects.aget_or_create(
        user=info.context.request.user,
        client=info.context.request.client,
        instance_id=input.instance_id,
    )
    
   

    # Check if room exists.

    print(settings.LIVEKIT)

    lkapi = api.LiveKitAPI(
        url=settings.LIVEKIT["API_URL"],
        api_key=settings.LIVEKIT["API_KEY"],
        api_secret=settings.LIVEKIT["API_SECRET"],
    )

    room_info = await lkapi.room.create_room(
        api.CreateRoomRequest(name=agent.streamlit_room_id),
    )

    token = (
        api.AccessToken(
            api_key=settings.LIVEKIT["API_KEY"],
            api_secret=settings.LIVEKIT["API_SECRET"],
        )
        .with_identity("agent-" + str(agent.id))
        .with_name("agent-" + str(agent.id))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=agent.streamlit_room_id,
            )
        )
        .to_jwt()
    )

    print(token)

    stream, _ = await models.Stream.objects.aupdate_or_create(
        title=input.title or "default", agent=agent, defaults=dict(token=token)
    )

    
    return stream


@strawberry.input
class JoinStreamInput:
    id: strawberry.ID


async def join_video_stream(info: Info, input: JoinStreamInput) -> types.Stream:
    creator = info.context.request.user


    agent, _ = await models.Agent.objects.get(id=id)

    token = (
        api.AccessToken()
        .with_identity(agent.id)
        .with_name(agent.name)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=agent.streamlit_room_id,
            )
        )
        .to_jwt()
    )

    exp = await models.Stream.objects.acreate(
        title=input.title or "Untitled", agent=agent, token=token
    )

    return exp


@strawberry.input
class LeaveStreamInput:
    id: strawberry.ID


async def leave_video_stream(info: Info, input: LeaveStreamInput) -> types.Stream:

    exp = await models.Stream.objects.aget(id=input.id)

    i

    await exp.delete()

    return exp


