import strawberry
from asgiref.sync import async_to_sync
from bridge import calls, inputs, streams
from bridge import models
from django.db.models import Q, QuerySet
import strawberry_django


@strawberry_django.order_type(models.Stream)
class StreamOrder:
    created_at: strawberry.auto
    title: strawberry.auto


@strawberry_django.filter_type(models.Agent, description="Filter for agents")
class AgentFilter:
    @strawberry_django.filter_field
    def ids(self, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}id__in": value})

    @strawberry_django.filter_field
    def search(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}client__name__icontains": value}) | Q(**{f"{prefix}client__client_id__icontains": value})

    @strawberry_django.filter_field(description="Agents running as this client (its OAuth client id), as rekuest knows it too.")
    def client_id(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}client__client_id": value})

    @strawberry_django.filter_field(description="Agents running for this user (the `sub` their token carries).")
    def user_sub(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}user__sub": value})


@strawberry_django.filter_type(models.Stream, description="Filter for streams")
class StreamFilter:
    @strawberry_django.filter_field
    def ids(self, value: list[strawberry.ID], prefix: str) -> Q:
        return Q(**{f"{prefix}id__in": value})

    @strawberry_django.filter_field
    def search(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}title__icontains": value}) | Q(**{f"{prefix}key__icontains": value})

    @strawberry_django.filter_field(description="Streams of this agent.")
    def agent(self, value: strawberry.ID, prefix: str) -> Q:
        return Q(**{f"{prefix}agent_id": value})

    @strawberry_django.filter_field(description="Streams of the agent running as this client (its OAuth client id), as rekuest knows it too.")
    def client_id(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}agent__client__client_id": value})

    @strawberry_django.filter_field(description="Streams of agents running for this user (the `sub` their token carries).")
    def user_sub(self, value: str, prefix: str) -> Q:
        return Q(**{f"{prefix}agent__user__sub": value})

    @strawberry_django.filter_field(description="Only streams their agent publishes right now (true), or does not (false).")
    def live(self, value: bool, queryset: QuerySet, prefix: str) -> tuple[QuerySet, Q]:
        # The queryset is built in a worker thread, so LiveKit is asked synchronously: once
        # for the rooms, once per agent room that is up.
        published = Q(pk__in=[])
        for agent_id, keys in async_to_sync(streams.live_tracks)().items():
            if keys:
                published |= Q(**{f"{prefix}agent_id": agent_id, f"{prefix}key__in": sorted(keys)})
        return queryset, (published if value else ~published)


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
        ids = calls.call_ids(names)
        predicate = Q(**{f"{prefix}id__in": ids})
        return queryset, (predicate if value else ~predicate)
