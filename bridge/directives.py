from typing import Optional
import strawberry
from strawberry.schema_directive import Location


@strawberry.schema_directive(locations=[Location.INPUT_OBJECT])
class unionElementOf:
    union: str = strawberry.field()
    discriminator: str = strawberry.field()
    key: str = strawberry.field()
