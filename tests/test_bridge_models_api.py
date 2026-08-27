import hashlib
import struct
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_ai_gateway.api.bridge_models import create_bridge_models_router
from local_ai_gateway.model_store import ModelStore


def _gguf_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def minimal_gguf() -> bytes:
    metadata = b"".join(
        [
            _gguf_string("general.name") + struct.pack("<I", 8) + _gguf_string("bridge-test"),
            _gguf_string("general.architecture") + struct.pack("<I", 8) + _gguf_string("llama"),
        ]
    )
    return b"GGUF" + struct.pack("<IQQ", 3, 0, 2) + metadata


class FakeRuntime:
    def __init__(self):
        self.started_with = None
        self.stopped = False

    def status(self):
        return {
            "runtime": "llama.cpp",
            "running": self.started_with is not None and not self.stopped,
            "model_sha256": self.started_with,
            "base_url": "http://127.0.0.1:8081",
        }

    def start(self, identifier, context_size=None, threads=None, api_key=None):
        self.started_with = identifier
        self.stopped = False
        return self.status()

    def stop(self):
        self.stopped = True
        return self.status()

    def restart(self, identifier=None, context_size=None, threads=None, api_key=None):
        self.started_with = identifier or self.started_with
        self.stopped = False
        return self.status()


def make_client(tmp_path: Path):
    app = FastAPI()
    runtime = FakeRuntime()
    app.include_router(
        create_bridge_models_router(
            store=ModelStore(tmp_path), runtime=runtime, auth_checker=lambda _request: None
        )
    )
    return TestClient(app), runtime


def upload_model(client: TestClient, payload: bytes):
    digest = hashlib.sha256(payload).hexdigest()
    begin = client.post(
        "/bridge/v1/transfers",
        json={"filename": "phone-model.gguf", "size_bytes": len(payload), "sha256": digest},
    )
    assert begin.status_code == 200
    transfer = begin.json()["transfer"]
    chunk = client.put(
        f"/bridge/v1/transfers/{transfer['id']}/chunk",
        headers={"X-Upload-Offset": "0", "Content-Type": "application/octet-stream"},
        content=payload,
    )
    assert chunk.status_code == 200
    done = client.post(f"/bridge/v1/transfers/{transfer['id']}/complete")
    assert done.status_code == 200
    return done.json()["model"]


def test_transfer_lookup_and_selection_api(tmp_path: Path):
    client, _runtime = make_client(tmp_path)
    payload = minimal_gguf()
    model = upload_model(client, payload)

    listing = client.get("/bridge/v1/models")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["models"][0]["available"] is True

    lookup = client.get(f"/bridge/v1/models/lookup?sha256={model['sha256']}")
    assert lookup.status_code == 200
    assert lookup.json()["available"] is True

    selected = client.post(f"/bridge/v1/models/{model['sha256']}/select")
    assert selected.status_code == 200
    assert selected.json()["model"]["active"] is True


def test_resumable_chunk_rejects_wrong_offset(tmp_path: Path):
    client, _runtime = make_client(tmp_path)
    payload = minimal_gguf()
    digest = hashlib.sha256(payload).hexdigest()
    begin = client.post(
        "/bridge/v1/transfers",
        json={"filename": "offset.gguf", "size_bytes": len(payload), "sha256": digest},
    ).json()["transfer"]

    first = client.put(
        f"/bridge/v1/transfers/{begin['id']}/chunk",
        headers={"X-Upload-Offset": "0"},
        content=payload[:10],
    )
    assert first.status_code == 200
    conflict = client.put(
        f"/bridge/v1/transfers/{begin['id']}/chunk",
        headers={"X-Upload-Offset": "0"},
        content=payload[10:],
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["expected_offset"] == 10


def test_runtime_start_selects_transferred_model(tmp_path: Path):
    client, runtime = make_client(tmp_path)
    model = upload_model(client, minimal_gguf())

    response = client.post(
        "/bridge/v1/runtime/start",
        json={"model": model["sha256"], "context_size": 2048, "threads": 4},
    )
    assert response.status_code == 200
    assert runtime.started_with == model["sha256"]
    assert response.json()["running"] is True

    stopped = client.post("/bridge/v1/runtime/stop")
    assert stopped.status_code == 200
    assert stopped.json()["running"] is False
