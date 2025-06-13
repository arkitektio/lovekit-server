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
from livekit import api as lapi
from django.conf import settings






async def ensure_stream(info: Info, input: inputs.EnsureStreamInput) -> str:


    streamer, _ = await models.Streamer.objects.aget_or_create(
        user=info.context.request.user,
        client=info.context.request.client,
    )
    
    
    broadcast = await models.Broadcast.objects.select_related("solobroadcast__streamer", "collaborativebroadcast").aget(id=input.broadcast)
    
    if broadcast.solobroadcast:
        assert streamer == broadcast.solobroadcast.streamer, "You are not the owner of this solo broadcast."
        
    elif broadcast.collaborativebroadcast:
        assert streamer in await broadcast.collaborative_broadcast.streamers.aall(), "You are not a member of this collaborative broadcast."
        
    else:
        raise ValueError("Broadcast must be either a solo or collaborative broadcast.")
    

    lkapi = api.get_api()

    token = (
        lapi.AccessToken(
            api_key=settings.LIVEKIT["API_KEY"],
            api_secret=settings.LIVEKIT["API_SECRET"],
        )
        .with_identity(streamer.streamlit_participant_id)
        .with_name(streamer.streamlit_participant_id)
        .with_grants(
            lapi.VideoGrants(
                room_join=True,
                room=broadcast.streamlit_room_id,
            )
        )
        .to_jwt()
    )

    print(token)

    stream, _ = await models.Stream.objects.aupdate_or_create(
        title=input.title or "default", broadcast=broadcast, streamer=streamer, kind=input.kind
    )

    
    return token



async def join_broadcast(info: Info, input: inputs.JoinBroadcastInput) -> str:
    creator = info.context.request.user


    broadcast = await models.Broadcast.objects.aget(id=input.broadcast)
    
    

    token = (
        lapi.AccessToken(
            api_key=settings.LIVEKIT["API_KEY"],
            api_secret=settings.LIVEKIT["API_SECRET"],
        )
        .with_identity("user-" + str(creator.id))
        .with_name(creator.username)
        .with_grants(
            lapi.VideoGrants(
                room_join=True,
                room=broadcast.streamlit_room_id,
                can_publish=False,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    return token




