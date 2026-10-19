"""lovekit's model signals: what it declares to the hub's rekuest, and that a declaration reaches it signed.

The save goes to a real local HTTP server standing in for rekuest's signal intake, and is
checked the way rekuest checks it (the instance-key JWT, the body).
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from joserfc.jwk import OKPKey

from arkitekt_service import trust
from lovekit_server.service import service

EXPECTED = {
    "@lovekit/stream": ["CREATED", "UPDATED", "DELETED"],
}

KEY = OKPKey.generate_key("Ed25519")

DECLARE = """
mutation ($input: DeclareStreamsInput!) { declareStreams(input: $input) { id key } }
"""


class _Intake:
    def __init__(self) -> None:
        self.received: list[dict] = []
        intake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers["Content-Length"]))
                intake.received.append({"path": self.path, "headers": dict(self.headers), "body": body, "json": json.loads(body)})
                self.send_response(202)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    async def settled(self, quiet: float = 0.5, timeout: float = 10) -> list[dict]:
        """Everything received, once nothing more arrived for ``quiet`` seconds."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        count = -1
        while loop.time() < deadline and count != len(self.received):
            count = len(self.received)
            await asyncio.sleep(quiet)
        return list(self.received)


@pytest.fixture
def intake(settings):
    server = _Intake()
    settings.REKUEST_SERVICE = {"REKUEST_URL": server.url, "SERVICE": "lovekit"}
    settings.INSTANCE = {
        "PRIVATE_KEY": KEY.as_pem(private=True).decode(),
        "TRUST_JWKS": {"keys": [{**trust.public_jwk(KEY), "service": "live.arkitekt.lovekit"}]},
    }
    yield server
    server.server.shutdown()
    # Closed, not only stopped: a signal still queued for this intake is refused at once
    # instead of holding the one sender thread until its timeout.
    server.server.server_close()


def test_the_manifest_declares_every_model_signal():
    assert {s["identifier"]: s["kinds"] for s in service.manifest()["signals"]} == EXPECTED


def test_the_manifest_lists_what_lovekit_hosts_with_its_descriptors():
    hosted = {s["identifier"]: s for s in service.manifest()["structures"]}
    assert set(hosted) == {"@lovekit/agent", "@lovekit/stream"}
    assert [(d["key"], d["type"]) for d in hosted["@lovekit/stream"]["descriptors"]] == [("@lovekit/stream_kind", "STRING")]
    # The signal of a structure carries exactly the keys the structure declares.
    for signal in service.manifest()["signals"]:
        assert signal["descriptors"] == [d["key"] for d in hosted[signal["identifier"]]["descriptors"]]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@pytest.mark.docker
async def test_a_declaration_is_signalled_once_and_a_restart_not_at_all(intake, aexecute):
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": "camera"}, {"key": "microphone", "kind": "AUDIO"}]}})
    assert not res.errors, res.errors
    camera, microphone = (stream["id"] for stream in res.data["declareStreams"])

    received = await intake.settled()
    assert sorted((r["json"]["kind"], r["json"]["object"]) for r in received) == [("CREATED", camera), ("CREATED", microphone)]
    by_object = {r["json"]["object"]: r for r in received}
    assert by_object[microphone]["json"]["descriptors"] == {"@lovekit/stream_kind": "audio"}
    first = received[0]
    assert trust.verify("POST", first["path"], first["body"], first["headers"]["Authorization"], audience="live.arkitekt.rekuest").issuer == "live.arkitekt.lovekit"

    # The agent restarts with the same streams: the hub hears nothing.
    intake.received.clear()
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": "camera"}, {"key": "microphone", "kind": "AUDIO"}]}})
    assert not res.errors, res.errors
    assert await intake.settled() == []

    # It stops offering the microphone.
    res = await aexecute(DECLARE, {"input": {"streams": [{"key": "camera"}]}})
    assert not res.errors, res.errors
    assert [(r["json"]["kind"], r["json"]["object"]) for r in await intake.settled()] == [("DELETED", microphone)]
