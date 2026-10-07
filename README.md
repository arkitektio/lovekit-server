# lovekit-server

The live video and audio service of an [Arkitekt](https://arkitekt.live) hub. It maps the
hub's users and apps onto rooms of a [LiveKit](https://livekit.io) server and hands out the
tokens to join them. It carries no media itself: once a client holds a token, it talks to
LiveKit directly. It is registered as `live.arkitekt.lovekit` and has a python client,
[`lovekit`](https://github.com/jhnnsrs/lovekit).

## What it stores

| Concept | What it is |
| --- | --- |
| `Streamer` | An app instance of a user that publishes: the client, the user, and the instance id. |
| `SoloBroadcast` | A titled broadcast with one streamer. A title is unique per streamer. |
| `CollaborativeBroadcast` | A titled broadcast several streamers publish into. A title is unique. |
| `Stream` | One track a streamer publishes into a broadcast: its kind and title. |

Each broadcast is one LiveKit room, named `broadcast-<id>`. A streamer joins as the
participant `streamer-<id>`, a viewer as `user-<id>`.

## API

GraphQL is served at `/graphql` (HTTP and WebSocket), with the SDL at `/schema`.

| Operations | What they do |
| --- | --- |
| `ensureSoloBroadcast`, `ensureCollaborativeBroadcast` | Get or create the broadcast, and create its room on LiveKit. |
| `ensureStream` | Get or create a stream in a broadcast, and return a LiveKit token that may join the room and publish. |
| `joinBroadcast` | Return a LiveKit token that may join the room and subscribe, but not publish. |
| `streams`, `soloBroadcasts`, `collaborativeBroadcasts` (and one by id) | The stored rows. |
| `streams` (subscription) | Stream updates as they happen. |

## Hub integration

Declared in [`lovekit_server/contract.py`](lovekit_server/contract.py):

- **Needs**: the `livekit` peer, whose URL, API key and API secret the contract writes into
  the `livekit` config block; `media` storage; tokens issued by lok.

It defines no scopes or roles of its own, does not register with rekuest and offers no
actions.

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
server in dev mode. It needs a running Docker daemon, and the host ports 5555 and 7780 free:
unlike the other services' suites, this stack pins its ports, so two runs cannot share a
machine.

## Releases

Releases are tags: a push to `main` cuts a stable version, a push to `next` a release
candidate. Each one publishes `jhnnsrs/lovekit` under its version (`X.Y.Z`, `X.Y`, `X`),
plus `latest` from `main` and `next` from `next`. The `version` in `pyproject.toml` is a
placeholder. Release notes are on
[GitHub Releases](https://github.com/arkitektio/lovekit-server/releases); `CHANGELOG.md` is
frozen.
