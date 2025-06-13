import hashlib
import json
import logging
from typing import Any, Dict, List, Tuple

import strawberry
import strawberry_django
from kante.types import Info
from bridge import types, models, inputs, api

logger = logging.getLogger(__name__)
from django.contrib.auth import get_user_model
from livekit.protocol.room import ListRoomsRequest, CreateRoomRequest
from django.conf import settings


async def ensure_solo_broadcast(info: Info, input: inputs.EnsureSoloBroadcastInput) -> types.SoloBroadcast:


    streamer, _ = await models.Streamer.objects.aget_or_create(
        user=info.context.request.user,
        client=info.context.request.client,
    )
    
    broadcast, _ = await models.SoloBroadcast.objects.aget_or_create(
        streamer=streamer,
        title=input.title or "Untitled",
    )
    
    lkapi = api.get_api()

    room_info = await lkapi.room.create_room(
        CreateRoomRequest(name=broadcast.streamlit_room_id),
    )
    
    
    
    return broadcast


async def ensure_collaborative_broadcast(
    info: Info, input: inputs.EnsureCollaborativeBroadcastInput
) -> types.CollaborativeBroadcast:
    streamer, _ = await models.Streamer.objects.aget_or_create(
        user=info.context.request.user,
        client=info.context.request.client,
    )
    broadcast, _ = await models.CollaborativeBroadcast.objects.aget_or_create(
        title=input.title or "Untitled",
        defaults={"streamers": [streamer]},
    )
    
    lkapi = api.get_api()

    room_info = await lkapi.room.create_room(
        api.CreateRoomRequest(name=broadcast.streamlit_room_id),
    )

    return broadcast




