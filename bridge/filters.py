import strawberry
from bridge import inputs
from bridge import models
import strawberry_django


@strawberry_django.order(models.Agent)
class AgentOrder:
    created_at: strawberry.auto


@strawberry_django.order(models.Stream)
class StreamOrder:
    created_at: strawberry.auto


@strawberry_django.filter(models.Agent, description="Filter for Dask Clusters")
class AgentFilter:
    """Filter for Dask Clusters"""

    ids: list[strawberry.ID] | None = None
    search: str | None = None
    pass

    def filter_search(self, queryset, search):
        return queryset.filter(name__icontains=search)

    def filter_ids(self, queryset, ids):
        return queryset.filter(id__in=ids)




@strawberry_django.filter(models.Stream, description="Filter for Streams")
class StreamFilter:
    """Filter for Dask Clusters"""

    ids: list[strawberry.ID] | None = None
    search: str | None = None
    pass

    def filter_search(self, queryset, search):
        return queryset.filter(name__icontains=search)

    def filter_ids(self, queryset, ids):
        return queryset.filter(id__in=ids)
