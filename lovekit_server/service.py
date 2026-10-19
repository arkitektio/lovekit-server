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

A full member shares an agent with a guest of the organization by putting it in a collaboration:
its streams are part of it, so the guest sees each one the agent offers, also those it declares
later. A stream put in alone is seen alone; its agent, and with it the stream's siblings, is not
brought along (no ``depends``), and watching it is refused: a watch token opens the agent's whole
room, every track in it (``bridge.graphql.mutations.stream``). Calls, not hosted, are in no
collaboration.
"""

from arkitekt_service.service import Service, organization_of

from bridge import models
from lovekit_server.contract import contract

service = Service("lovekit", hosts=contract.description.hosts, description="Live video and audio: the streams agents offer, and calls.")


# --- Structures: what lovekit hosts ---------------------------------------------------

agent = service.structure(models.Agent, "@lovekit/agent")
stream = service.structure(models.Stream, "@lovekit/stream", describe=lambda stream: {"@lovekit/stream_kind": str(stream.kind)})


# --- Signals: what lovekit announces --------------------------------------------------

service.model_signal(stream, organization=organization_of("agent.organization"))


# --- Collaborations: what is part of what ---------------------------------------------

# An agent is the user's and the client's it runs as, not part of either: a user (or a client)
# never brings every agent it runs, and their streams, into a collaboration.
service.not_part_of(models.Agent, "user", "client")
