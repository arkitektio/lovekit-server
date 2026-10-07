"""What this image answers a hub's installer: ``arkitekt-service <verb>`` (see ``arkitekt_service.contract``).

The installer knows the hub; how this release spells its config is written here, with the
settings it is read by. A key renamed in ``configuration.py`` is renamed in :func:`render` in
the same commit, and no installer has to learn of it.
"""

from __future__ import annotations

from arkitekt_service.contract import JSON, Contract, Description, Facts, Needs, Offers, Start, blocks

from lovekit_server.configuration import Settings


def render(facts: Facts) -> dict[str, JSON]:
    """This release's config for the hub ``facts`` describes."""
    document: dict[str, JSON] = blocks.server(facts)
    livekit = facts.peers.get("livekit")
    if livekit is not None:
        document["livekit"] = {"api_key": livekit.settings["api_key"], "api_secret": livekit.settings["api_secret"], "api_url": livekit.url}
    return document


contract = Contract(
    description=Description(
        name="lovekit",
        identifier="live.arkitekt.lovekit",
        summary="Live video and audio rooms.",
        needs=Needs(storage=["media"], instance_key=False, peers=["livekit"]),
        offers=Offers(),
    ),
    settings=Settings,
    render=render,
    # How this service is started: there is no script beside it. `arkitekt-service serve`
    # (and `debug`) become these, so they get the container's signals themselves.
    serve=Start(("daphne", "-b", "0.0.0.0", "-p", "80", "--websocket_timeout", "-1", "lovekit_server.asgi:application")),
    debug=Start(("python", "manage.py", "runserver", "0.0.0.0:80")),
)
