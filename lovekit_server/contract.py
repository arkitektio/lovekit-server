"""What this image answers a hub's installer: ``arkitekt-service <verb>`` (see ``arkitekt_service.contract``).

The installer knows the hub; how this release spells its config is written here, with the
settings it is read by. A key renamed in ``configuration.py`` is renamed in :func:`render` in
the same commit, and no installer has to learn of it.
"""

from __future__ import annotations

from arkitekt_service.contract import JSON, Contract, Description, Descriptor, Facts, Hosts, Job, Needs, Offers, Role, Scope, Signal, Start, Structure, blocks

from lovekit_server.configuration import Settings

#: What an app may do here on a user's behalf: defined at the coordination server when the hub
#: enrols. Every root field of the schema asks for one of them (`AuthExtension(scopes=...)`).
SCOPES = [
    Scope(key="lovekit_watch", description="Watch live streams and agents."),
    Scope(key="lovekit_publish", description="Stream live video and audio as an agent."),
    Scope(key="lovekit_call", description="Start and join calls, and invite others to them."),
    Scope(key="lovekit_share", description="Share streams with people outside your organization through collaborations."),
    Scope(key="lovekit_all", description="Do everything in Lovekit on your behalf.", is_all_scope=True),
]

#: What a member of an organization may do here.
ROLES = [
    Role(key="lovekit_admin", description="Full control of Lovekit in this organization.", is_admin_role=True),
    Role(key="lovekit_editor", description="Stream, start calls and share.", is_default_role=True),
]

#: The role every write asks for, and the one that holds every role.
EDITOR = "lovekit_editor"
ADMIN = "lovekit_admin"


#: What exists on a hub because this service is there: said here, as data, so the hub knows it from
#: the image. ``service.py`` binds each of these to its model and refuses anything not said here.
STREAM_DESCRIPTORS = [
    Descriptor(key="@lovekit/stream_kind", type="STRING", description="What the stream carries: video (pictures, e.g. from a camera) or audio (sound, e.g. from a microphone)"),
]

HOSTS = Hosts(
    structures=[
        Structure(
            identifier="@lovekit/agent",
            label="Stream Agent",
            description="An app instance that offers live streams, from its cameras or microphones, in one LiveKit room: one per client, user and organization.",
        ),
        Structure(
            identifier="@lovekit/stream",
            label="Live Stream",
            description="One live stream an agent offers: video or audio from one source (a camera or webcam, a detector, a microphone), published as a LiveKit track and the same across the agent's restarts.",
            descriptors=STREAM_DESCRIPTORS,
        ),
    ],
    signals=[
        Signal(
            identifier="@lovekit/stream",
            kinds=["CREATED", "UPDATED", "DELETED"],
            descriptors=[descriptor.key for descriptor in STREAM_DESCRIPTORS],
            description="An agent declared a live video or audio stream for the first time, changed one, or stopped offering one. Not whether it is live right now.",
        ),
    ],
)


def render(facts: Facts) -> dict[str, JSON]:
    """This release's config for the hub ``facts`` describes."""
    document: dict[str, JSON] = blocks.server(facts)
    livekit = facts.peers.get("livekit")
    if livekit is not None:
        document["livekit"] = {"api_key": livekit.settings["api_key"], "api_secret": livekit.settings["api_secret"], "api_url": livekit.url}
    document["instance"] = blocks.instance(facts)
    hook = blocks.rekuest_hook(facts)
    if hook is not None:
        document["rekuest_hook"] = hook
    return document


contract = Contract(
    description=Description(
        name="lovekit",
        identifier="live.arkitekt.lovekit",
        summary="Live video and audio rooms.",
        needs=Needs(storage=["media"], instance_key=True, peers=["livekit", "rekuest"], scopes=SCOPES, roles=ROLES),
        offers=Offers(endpoints={"rekuest_service": "_rekuest/service"}),
        requires={"rekuest": ">=6"},
        hosts=HOSTS,
    ),
    settings=Settings,
    render=render,
    # How this service is started: there is no script beside it. `arkitekt-service serve`
    # (and `debug`) become these, so they get the container's signals themselves.
    serve=Start(("daphne", "-b", "0.0.0.0", "-p", "80", "--websocket_timeout", "-1", "lovekit_server.asgi:application")),
    debug=Start(("python", "manage.py", "runserver", "0.0.0.0:80")),
    jobs={
        "ensureadmin": Job(("ensureadmin",), "Create the operator account the config names"),
    },
    setup=("ensureadmin",),
)
