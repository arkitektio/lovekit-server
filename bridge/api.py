

from livekit import api
from django.conf import settings
# Check if room exists.

def get_api() -> api.LiveKitAPI:
    
    lkapi = api.LiveKitAPI(
        url=settings.LIVEKIT["API_URL"],
        api_key=settings.LIVEKIT["API_KEY"],
        api_secret=settings.LIVEKIT["API_SECRET"],
    )
    
    return lkapi
