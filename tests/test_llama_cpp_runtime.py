import hashlib
import socket
import stat
import struct
from pathlib import Path

import pytest

from local_ai_gateway.model_store import ModelStore
from local_ai_gateway.runtime.llama_cpp import LlamaCppRuntime, RuntimeUnavailableError


def _gguf_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def minimal_gguf() -> bytes:
    metadata = b"".join(
        [
            _gguf_string("general.name") + struct.pack("<I", 8) + _gguf_string("runtime-test"),
            _gguf_string("general.architecture") + struct.pack("<I", 8) + _gguf_string("llama"),
        ]
    )
    return b"GGUF" + struct.pack("<IQQ", 3, 0, 2) + metadata


def open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def add_model(store: ModelStore):
    payload = minimal_gguf()
    started = store.begin_upload("runtime.gguf", len(payload), hashlib.sha256(payload).hexdigest())
    transfer = started["transfer"]
    store.append_chunk(transfer["id"], 0, payload)
    return store.complete_upload(transfer["id"])


def fake_server_executable(tmp_path: Path) -> Path:
    script = tmp_path / "fake-llama-server"
    script.write_text(
        "#!/bin/sh\n"
        "port=8081\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = \"--port\" ]; then port=$2; shift 2; continue; fi\n"
        "  shift\n"
        "done\n"
        "exec python3 -m http.server \"$port\" --bind 127.0.0.1\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_runtime_runs_only_on_loopback_and_stops_owned_process(tmp_path: Path):
    store = ModelStore(tmp_path / "store")
    model = add_model(store)
    port = open_port()
    runtime = LlamaCppRuntime(
        store=store,
        port=port,
        executable=str(fake_server_executable(tmp_path)),
        startup_timeout=5,
    )

    status = runtime.start(model["sha256"], context_size=2048, threads=2)
    assert status["running"] is True
    assert status["host"] == "127.0.0.1"
    assert status["model_sha256"] == model["sha256"]
    assert "--gpu-layers" in status["command"]
    assert "0" in status["command"]

    stopped = runtime.stop()
    assert stopped["running"] is False


def test_runtime_requires_a_real_executable(tmp_path: Path):
    store = ModelStore(tmp_path / "store")
    model = add_model(store)
    runtime = LlamaCppRuntime(store=store, port=open_port(), executable="/does/not/exist")

    with pytest.raises(RuntimeUnavailableError):
        runtime.start(model["sha256"])


def test_runtime_rejects_non_loopback_binding(tmp_path: Path):
    with pytest.raises(ValueError, match="loopback"):
        LlamaCppRuntime(store=ModelStore(tmp_path / "store"), host="0.0.0.0")
