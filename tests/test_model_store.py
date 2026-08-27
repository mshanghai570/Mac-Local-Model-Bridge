import hashlib
import struct
from pathlib import Path

import pytest

from local_ai_gateway.model_store import (
    FilenameConflictError,
    IntegrityError,
    ModelStore,
    TransferOffsetError,
)


def _gguf_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def minimal_gguf(name: str = "test-model", architecture: str = "llama") -> bytes:
    metadata = b"".join(
        [
            _gguf_string("general.name") + struct.pack("<I", 8) + _gguf_string(name),
            _gguf_string("general.architecture") + struct.pack("<I", 8) + _gguf_string(architecture),
        ]
    )
    return b"GGUF" + struct.pack("<IQQ", 3, 0, 2) + metadata


def begin(store: ModelStore, payload: bytes, filename: str = "model.gguf"):
    return store.begin_upload(filename, len(payload), hashlib.sha256(payload).hexdigest())


def test_upload_resumes_and_only_promotes_after_integrity_check(tmp_path: Path):
    payload = minimal_gguf()
    store = ModelStore(tmp_path)
    started = begin(store, payload)
    transfer = started["transfer"]
    assert started["status"] == "created"
    assert transfer["bytes_received"] == 0

    first = store.append_chunk(transfer["id"], 0, payload[:11])
    assert first["bytes_received"] == 11
    assert store.list_models() == []

    resumed = begin(store, payload)
    assert resumed["status"] == "resumed"
    assert resumed["transfer"]["id"] == transfer["id"]
    assert resumed["transfer"]["bytes_received"] == 11

    with pytest.raises(TransferOffsetError):
        store.append_chunk(transfer["id"], 0, payload[11:])

    store.append_chunk(transfer["id"], 11, payload[11:])
    completed = store.complete_upload(transfer["id"])
    assert completed["available"] is True
    assert completed["metadata"]["format"] == "gguf"
    assert completed["metadata"]["name"] == "test-model"
    assert (tmp_path / "files" / "model.gguf").read_bytes() == payload
    assert not (tmp_path / "files" / "model.gguf.part").exists()


def test_checksum_failure_never_promotes_part_file(tmp_path: Path):
    payload = minimal_gguf()
    store = ModelStore(tmp_path)
    started = begin(store, payload)
    transfer = started["transfer"]
    corrupt = payload[:-1] + bytes([payload[-1] ^ 0xFF])
    store.append_chunk(transfer["id"], 0, corrupt)

    with pytest.raises(IntegrityError, match="SHA-256 mismatch"):
        store.complete_upload(transfer["id"])

    assert store.list_models() == []
    assert (tmp_path / "files" / "model.gguf.part").exists()
    assert store.get_transfer(transfer["id"])["status"] == "failed"

    restarted = begin(store, payload)
    assert restarted["status"] == "restarted"
    assert restarted["transfer"]["bytes_received"] == 0
    assert not (tmp_path / "files" / "model.gguf.part").exists()


def test_tensor_truncated_gguf_never_becomes_available(tmp_path: Path):
    metadata = _gguf_string("general.name") + struct.pack("<I", 8) + _gguf_string("truncated")
    tensor = _gguf_string("weight") + struct.pack("<I", 1) + struct.pack("<QIQ", 1, 0, 0)
    # The descriptor declares one 4-byte F32 tensor but intentionally omits its aligned data section.
    payload = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + metadata + tensor
    store = ModelStore(tmp_path)
    started = begin(store, payload, "truncated.gguf")
    transfer = started["transfer"]
    store.append_chunk(transfer["id"], 0, payload)

    with pytest.raises(IntegrityError, match="truncated"):
        store.complete_upload(transfer["id"])

    assert store.list_models() == []


def test_bad_gguf_never_becomes_available(tmp_path: Path):
    payload = b"not-a-gguf-file"
    store = ModelStore(tmp_path)
    started = begin(store, payload)
    transfer = started["transfer"]
    store.append_chunk(transfer["id"], 0, payload)

    with pytest.raises(IntegrityError, match="GGUF"):
        store.complete_upload(transfer["id"])

    assert store.list_models() == []
    assert (tmp_path / "files" / "model.gguf.part").exists()


def test_cancelled_transfer_can_resume_and_model_selection_is_persistent(tmp_path: Path):
    payload = minimal_gguf("another-model")
    store = ModelStore(tmp_path)
    started = begin(store, payload, "another.gguf")
    transfer = started["transfer"]
    store.append_chunk(transfer["id"], 0, payload[:20])
    cancelled = store.cancel_transfer(transfer["id"])
    assert cancelled["status"] == "cancelled"

    resumed = begin(store, payload, "another.gguf")
    assert resumed["status"] == "resumed"
    current = resumed["transfer"]
    store.append_chunk(current["id"], current["bytes_received"], payload[current["bytes_received"]:])
    completed = store.complete_upload(current["id"])
    selected = store.select_model(completed["sha256"])
    assert selected["active"] is True

    reopened = ModelStore(tmp_path)
    assert reopened.active_model()["sha256"] == completed["sha256"]
    removed = reopened.remove_model("another.gguf")
    assert removed["sha256"] == completed["sha256"]
    assert reopened.active_model() is None


def test_different_model_cannot_reuse_active_filename_staging_path(tmp_path: Path):
    store = ModelStore(tmp_path)
    first = minimal_gguf("first")
    second = minimal_gguf("second")
    first_transfer = begin(store, first, "same-name.gguf")["transfer"]
    store.append_chunk(first_transfer["id"], 0, first[:8])

    with pytest.raises(FilenameConflictError):
        begin(store, second, "same-name.gguf")
