import strawberry
from bridge import inputs
from bridge import models
import strawberry_django


@strawberry_django.order(models.Streamer)
class StreamerOrder:
    created_at: strawberry.auto


@strawberry_django.order(models.Stream)
class StreamOrder:
    created_at: strawberry.auto


@strawberry_django.filter(models.Streamer, description="Filter for Dask Clusters")
class StreamerFilter:
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


@strawberry_django.filter(models.SoloBroadcast, description="Filter for Solo Broadcasts")
class SoloBroadcastFilter:
    """Filter for Dask Clusters"""

    ids: list[strawberry.ID] | None = None
    search: str | None = None
    pass

    def filter_search(self, queryset, search):
        return queryset.filter(name__icontains=search)

    def filter_ids(self, queryset, ids):
        return queryset.filter(id__in=ids)



@strawberry_django.filter(models.CollaborativeBroadcast, description="Filter for Solo Broadcasts")
class CollaborativeBroadcastFilter:
    """Filter for Dask Clusters"""

    ids: list[strawberry.ID] | None = None
    search: str | None = None
    pass

    def filter_search(self, queryset, search):
        return queryset.filter(name__icontains=search)

    def filter_ids(self, queryset, ids):
        return queryset.filter(id__in=ids)
