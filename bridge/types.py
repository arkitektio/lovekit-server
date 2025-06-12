import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from authentikate.strawberry.types import Client, User
from bridge import enums, filters, models
from kante.types import Info


@strawberry_django.type(models.Agent, filters=filters.AgentFilter, pagination=True)
class Agent:
    id: strawberry.ID



@strawberry_django.type(models.Stream, filters=filters.StreamFilter,  pagination=True)
class Stream:
    id: strawberry.ID
    agent: Agent
    title: str

    @strawberry.field
    def token(self, info: Info) -> str:
        return self.token