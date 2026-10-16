import hashlib
import json
import logging
from typing import Any, Dict, List, Tuple

import strawberry
import strawberry_django
from kante.types import Info
from bridge import types, models, inputs, tokens

logger = logging.getLogger(__name__)
from django.contrib.auth import get_user_model






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
    

    stream, _ = await models.Stream.objects.aupdate_or_create(
        title=input.title or "default", broadcast=broadcast, streamer=streamer, kind=input.kind
    )

    # Its own identity per token: a second connection of this client (another
    # process, a reconnect) publishes beside the first instead of replacing it.
    return tokens.participant_token(
        broadcast.streamlit_room_id,
        kind="streamer",
        id=streamer.id,
        user=info.context.request.user,
        can_publish=True,
        can_publish_data=True,
        metadata={"streamer": streamer.id},
    )



async def join_broadcast(info: Info, input: inputs.JoinBroadcastInput) -> str:
    creator = info.context.request.user


    broadcast = await models.Broadcast.objects.aget(id=input.broadcast)
    
    

    # Its own identity per token: the same user watching in a second window
    # or on a second device joins beside the first instead of kicking it out.
    return tokens.participant_token(
        broadcast.streamlit_room_id,
        kind="user",
        id=creator.id,
        user=creator,
        can_publish=False,
    )




