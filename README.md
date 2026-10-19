# lovekit-server

The live video and audio service of an [Arkitekt](https://arkitekt.live) hub. It maps the
hub's users and apps onto rooms of a [LiveKit](https://livekit.io) server and hands out the
tokens to join them. It carries no media itself: once a client holds a token, it talks to
LiveKit directly. It is registered as `live.arkitekt.lovekit` and has a python client,
[`lovekit`](https://github.com/jhnnsrs/lovekit).

## What it stores

| Concept | What it is |
| --- | --- |
| `Agent` | An app instance that offers live streams: one per client, user and organization, the key rekuest gives its agents too. A restarted process is the same agent. |
| `Stream` | One live source an agent offers (a camera, a detector, a microphone) under a `key` of the agent's choosing, unique per agent and the same across its restarts. |
| `Call` | A multi-party room about some structures (`@mikro/image 42`), which everyone in its organization may join. |
| `CallInvite` | Someone asking someone else into a call. |

Each agent is one LiveKit room, `agent-<id>`, and each of its streams is the track named by
the stream's key in it. Only the agent publishes there, always as the participant
`agent-<id>`: a restarted process replaces the connection its predecessor left behind
(LiveKit tells the old one `DUPLICATE_IDENTITY`). Whoever watches joins as `user-<id>-<nonce>`
and may not publish. Whether a stream is live is LiveKit's answer, asked when it is read:
the agent publishes a track of that name. Each call is the room `call-<id>`.

## API

GraphQL is served at `/graphql` (HTTP and WebSocket), with the SDL at `/schema`. Everything
is scoped to the caller's organization.

| Operations | What they do |
| --- | --- |
| `declareStreams` | The caller's agent offers exactly these streams. A stream it declared before keeps its id, one it leaves out is removed, and one that did not change is not written. |
| `publishToken` | A LiveKit token for the caller's agent to publish into its room (after `declareStreams`). |
| `watchStream`, `watchAgent` | A LiveKit token to subscribe in the agent's room, but not publish. |
| `streams`, `agents` (and one by id) | The organization's agents and streams; `streams(filters: {live, agent, clientId, userSub})`. |
| `streams` (subscription) | Streams declared, changed and dropped, as they are (not whether they are live). |
| `ensureCall`, `addToCall`, `joinCall`, `inviteToCall`, `dismissCallInvite`, `calls`, `call`, `myCallInvites` | Calls. |
| `calls`, `callInvites` (subscriptions) | Calls starting and changing, invitations arriving. |

## Hub integration

Declared in [`lovekit_server/contract.py`](lovekit_server/contract.py):

- **Needs**: the `livekit` peer, whose URL, API key and API secret the contract writes into
  the `livekit` config block; the `rekuest` peer and an instance key, to announce streams;
  `media` storage; tokens issued by lok.
- **Hosts**: `@lovekit/agent` and `@lovekit/stream` (descriptor `@lovekit/stream_kind`), bound
  in [`lovekit_server/service.py`](lovekit_server/service.py). A stream's first declaration,
  a change and its removal are signalled (`CREATED`, `UPDATED`, `DELETED`); whether it is
  live is not.

It defines no scopes or roles of its own and offers no actions.

## Running

The image is `jhnnsrs/lovekit`. It has no default command, and starting it takes two steps:

```sh
arkitekt-service run migrate   # wait for the database, apply migrations
arkitekt-service serve                          # serve on :80 (daphne), and nothing else
```

It needs Postgres, Redis and a LiveKit server it can reach with an API key and secret.

## Configuration

The service reads `config.yaml`, or the file named by `ARKITEKT_CONFIG_FILE`; any value can
be overridden by an environment variable (`POSTGRES__HOST`). `python manage.py
validate_settings` prints the configuration as the service reads it, with secrets redacted.

See [CONFIG.md](CONFIG.md) for every value.

## Development

```sh
uv sync
uv run pytest
```

The suite runs against a real stack, brought up by [dokker](https://github.com/jhnnsrs/dokker)
from `tests/integration/docker-compose.yaml`: Postgres (`jhnnsrs/daten:next`) and a LiveKit
server in dev mode (media over TCP 7782 and UDP 7783, so tests publish real tracks). It needs a running
Docker daemon, and those host ports and 5555 and 7780 free:
unlike the other services' suites, this stack pins its ports, so two runs cannot share a
machine.

## Releases

Releases are tags: a push to `main` cuts a stable version, a push to `next` a release
candidate. Each one publishes `jhnnsrs/lovekit` under its version (`X.Y.Z`, `X.Y`, `X`),
plus `latest` from `main` and `next` from `next`. The `version` in `pyproject.toml` is a
placeholder. Release notes are on
[GitHub Releases](https://github.com/arkitektio/lovekit-server/releases); `CHANGELOG.md` is
frozen.
