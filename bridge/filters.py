import strawberry
from asgiref.sync import async_to_sync
from bridge import calls, inputs
from bridge import models
from django.db.models import Q, QuerySet
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



@strawberry_django.order_type(models.Call)
class CallOrder:
    created_at: strawberry.auto


@strawberry_django.filter_type(models.Call, description="Filter for calls")
class CallFilter:
    @strawberry_django.filter_field
    def ids(self, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}id__in": value})

    @strawberry_django.filter_field
    def search(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}title__icontains": value})

    @strawberry_django.filter_field(description="Calls about this structure.")
    def about(self, value: inputs.StructureInput, queryset: QuerySet, prefix: str) -> tuple[QuerySet, Q]:
        structure = models.Structure.objects.filter(object=value.object, identifier=value.identifier).first()
        if not structure:
            return queryset.none(), Q()
        return queryset, Q(**{f"{prefix}about": structure})

    @strawberry_django.filter_field(description="Only calls whose LiveKit room is up (true) or down (false).")
    def live(self, value: bool, queryset: QuerySet, prefix: str) -> tuple[QuerySet, Q]:
        # The queryset is built in a worker thread, so LiveKit is asked
        # synchronously; one request answers for every call in the list.
        names = async_to_sync(calls.live_room_names)()
        ids = [int(name.removeprefix("call-")) for name in names if name.startswith("call-") and name[5:].isdigit()]
        predicate = Q(**{f"{prefix}id__in": ids})
        return queryset, (predicate if value else ~predicate)
