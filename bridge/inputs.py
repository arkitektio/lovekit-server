import strawberry


@strawberry.input
class CreateStreamInput:
    instance_id: str | None = None
    title: str | None = None
