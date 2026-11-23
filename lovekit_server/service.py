"""lovekit as a service of the hub: the models behind what its contract says it hosts.

What exists here (the structures, the descriptors of their objects, the signals and their kinds)
is declared once, as data, in ``lovekit_server.contract`` (``hosts``), so that a hub knows it from
the image. This module only binds it: each structure to its model and to what computes its
descriptors, each signal to the saves and deletes that send it. The GraphQL types answer
``descriptors`` from the same binding (``bridge.types``).

A stream is announced to its agent's organization when the agent declares it for the first time,
changes it, or stops offering it. ``declareStreams`` saves only what changed, so an agent that
restarts with the streams it had announces nothing. Whether a stream is live is LiveKit's and
is never signalled. Calls are not hosted here.

A full member shares an agent with a guest of the organization by putting it in a collaboration
(lok's, by its key): its streams are part of it, so the guest sees each one the agent offers, also
those it declares later, and may watch them: a watch token opens the agent's whole room, every
track in it (``bridge.graphql.mutations.stream``). A stream is never put in alone: its agent is its
whole (its required, cascading key), and a collaboration refuses a part without it. Calls, not
hosted, are in no collaboration.

Nothing here says which workflow made it (no ``created_through``, no history): an agent is the
identity an app runs as, made the first time it declares its streams, and kept across every
workflow after; its streams are what it declares, upserted by key. A workflow did not make them,
so sharing one (``shareWorkflow``) reports both as ``unknown`` and puts nothing in: handing out an
agent opens its whole room, and that is a member's decision, by hand.
"""

from arkitekt_service.service import Service, organization_of

from bridge import models
from lovekit_server.contract import contract

service = Service(
    "lovekit",
    hosts=contract.description.hosts,
    description="Live video and audio: the streams agents offer, and calls.",
)


# --- Structures: what lovekit hosts ---------------------------------------------------

agent = service.structure(models.Agent, "@lovekit/agent")
stream = service.structure(
    models.Stream,
    "@lovekit/stream",
    describe=lambda stream: {"@lovekit/stream_kind": str(stream.kind)},
)


# --- Signals: what lovekit announces --------------------------------------------------

service.model_signal(stream, organization=organization_of("agent.organization"))


# --- Collaborations: what is part of what ---------------------------------------------

# An agent is the user's and the client's it runs as, not part of either: a user (or a client)
# never brings every agent it runs, and their streams, into a collaboration.
service.not_part_of(models.Agent, "user", "client")
