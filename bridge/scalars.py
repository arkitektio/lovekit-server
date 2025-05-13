from typing import NewType

import strawberry

UntypedParams = strawberry.scalar(
    NewType("UntypedParams", object),
    description="UntypedParams represents an untyped options object returned by the Dask Gateway API.",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)
