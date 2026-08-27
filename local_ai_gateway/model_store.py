"""Durable, bounded-memory storage for GGUF models received by the Mac bridge.

The store deliberately separates model availability from transfer state. A model is
listed as available only after its expected byte count, SHA-256 digest, and basic
GGUF header have been verified and its ``.part`` file has been atomically promoted.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import struct
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Tuple


class ModelStoreError(Exception):
    """Base error raised for model-store operations."""


class ModelNotFoundError(ModelStoreError):
    """Raised when a requested model does not exist in the local store."""


class TransferNotFoundError(ModelStoreError):
    """Raised when a requested upload session does not exist."""


class TransferOffsetError(ModelStoreError):
    """Raised when a client tries to append at an offset other than the resume point."""

    def __init__(self, expected_offset: int, received_offset: int):
        self.expected_offset = expected_offset
        self.received_offset = received_offset
        super().__init__(
            "Upload offset mismatch: expected "
            f"{expected_offset}, received {received_offset}. Resume at the expected offset."
        )


class IntegrityError(ModelStoreError):
    """Raised when a completed upload fails checksum or GGUF validation."""


class InsufficientStorageError(ModelStoreError):
    """Raised before an upload would consume unavailable disk space."""


class FilenameConflictError(ModelStoreError):
    """Raised when a different model is already registered under the same filename."""


_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_MAX_METADATA_ENTRIES = 1_000_000
_COPY_BLOCK_SIZE = 1024 * 1024
# GGML tensor types 0-37: byte size and number of elements per encoded block.
# The map lets us validate tensor extents without ever loading tensor data.
_GGML_TYPE_LAYOUT: Tuple[Tuple[int, int], ...] = (
    (4, 1), (2, 1), (18, 32), (20, 32), (16, 32), (18, 32), (22, 32), (24, 32),
    (34, 32), (36, 32), (20, 256), (44, 256), (144, 256), (176, 256), (212, 256),
    (292, 256), (18, 256), (22, 256), (28, 256), (18, 256), (34, 32), (34, 256),
    (22, 256), (34, 256), (1, 1), (2, 1), (4, 1), (8, 1), (8, 1), (22, 256),
    (36, 32), (72, 32), (136, 32), (2, 1), (4, 1), (8, 1), (2, 1), (1, 1),
)


def _default_store_root() -> Path:
    configured = os.getenv("MODEL_STORE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "local-ai-gateway" / "models"


def _now() -> float:
    return time.time()


def _format_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    return f"{value / (1024 * 1024 * 1024):.2f} GB"


def _atomic_json_write(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    with open(temporary, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _safe_filename(name: str) -> str:
    candidate = Path((name or "").strip()).name
    if not candidate or candidate in {".", ".."} or candidate != name.strip():
        raise ModelStoreError("Model filename must be a plain filename without path components.")
    if not candidate.lower().endswith(".gguf"):
        raise ModelStoreError("Only .gguf model files are accepted by the Mac model store.")
    if len(candidate.encode("utf-8")) > 240:
        raise ModelStoreError("Model filename is too long.")
    return candidate


def _read_exact(handle: BinaryIO, length: int, file_size: int) -> bytes:
    if length < 0 or handle.tell() + length > file_size:
        raise IntegrityError("GGUF header is truncated.")
    value = handle.read(length)
    if len(value) != length:
        raise IntegrityError("GGUF header is truncated.")
    return value


def _read_u32(handle: BinaryIO, file_size: int) -> int:
    return struct.unpack("<I", _read_exact(handle, 4, file_size))[0]


def _read_i32(handle: BinaryIO, file_size: int) -> int:
    return struct.unpack("<i", _read_exact(handle, 4, file_size))[0]


def _read_u64(handle: BinaryIO, file_size: int) -> int:
    return struct.unpack("<Q", _read_exact(handle, 8, file_size))[0]


def _read_i64(handle: BinaryIO, file_size: int) -> int:
    return struct.unpack("<q", _read_exact(handle, 8, file_size))[0]


def _read_string(handle: BinaryIO, file_size: int, limit: int = 1024 * 1024) -> str:
    length = _read_u64(handle, file_size)
    if length > limit:
        raise IntegrityError("GGUF metadata string exceeds the supported safety limit.")
    return _read_exact(handle, int(length), file_size).decode("utf-8", errors="replace")


def _skip_bytes(handle: BinaryIO, amount: int, file_size: int) -> None:
    if amount < 0 or handle.tell() + amount > file_size:
        raise IntegrityError("GGUF metadata is truncated.")
    handle.seek(amount, os.SEEK_CUR)


def _read_or_skip_gguf_value(
    handle: BinaryIO,
    type_code: int,
    file_size: int,
    capture: bool,
) -> Any:
    """Read a compact GGUF metadata value or seek over it without buffering it."""
    scalar_sizes = {
        0: 1,  # uint8
        1: 1,  # int8
        2: 2,  # uint16
        3: 2,  # int16
        4: 4,  # uint32
        5: 4,  # int32
        6: 4,  # float32
        7: 1,  # bool
        10: 8,  # uint64
        11: 8,  # int64
        12: 8,  # float64
    }
    if type_code == 8:  # string
        value = _read_string(handle, file_size)
        return value if capture else None
    if type_code == 9:  # array
        element_type = _read_u32(handle, file_size)
        count = _read_u64(handle, file_size)
        if count > _MAX_METADATA_ENTRIES:
            raise IntegrityError("GGUF metadata array exceeds the supported safety limit.")
        if capture and count <= 64:
            return [
                _read_or_skip_gguf_value(handle, element_type, file_size, capture=True)
                for _ in range(int(count))
            ]
        for _ in range(int(count)):
            _read_or_skip_gguf_value(handle, element_type, file_size, capture=False)
        return None
    if type_code not in scalar_sizes:
        raise IntegrityError(f"Unsupported GGUF metadata value type {type_code}.")

    raw = _read_exact(handle, scalar_sizes[type_code], file_size)
    if not capture:
        return None
    if type_code == 0:
        return raw[0]
    if type_code == 1:
        return struct.unpack("<b", raw)[0]
    if type_code == 2:
        return struct.unpack("<H", raw)[0]
    if type_code == 3:
        return struct.unpack("<h", raw)[0]
    if type_code == 4:
        return struct.unpack("<I", raw)[0]
    if type_code == 5:
        return struct.unpack("<i", raw)[0]
    if type_code == 6:
        return struct.unpack("<f", raw)[0]
    if type_code == 7:
        return bool(raw[0])
    if type_code == 10:
        return struct.unpack("<Q", raw)[0]
    if type_code == 11:
        return struct.unpack("<q", raw)[0]
    return struct.unpack("<d", raw)[0]


def inspect_gguf(path: Path) -> Dict[str, Any]:
    """Read basic GGUF metadata without mapping or loading the model body into RAM."""
    file_size = path.stat().st_size
    if file_size < 24:
        raise IntegrityError("GGUF file is too small to contain a valid header.")

    wanted = {
        "general.name",
        "general.architecture",
        "general.description",
        "general.file_type",
        "general.quantization_version",
        "llama.context_length",
        "qwen2.context_length",
        "qwen3.context_length",
        "mistral.context_length",
        "gemma.context_length",
        "phi3.context_length",
    }
    captured: Dict[str, Any] = {}
    with open(path, "rb") as handle:
        magic = _read_exact(handle, 4, file_size)
        if magic != b"GGUF":
            raise IntegrityError("Uploaded file is not a GGUF model (invalid magic).")
        version = _read_u32(handle, file_size)
        if version < 2 or version > 4:
            raise IntegrityError(f"Unsupported GGUF version {version}.")
        tensor_count = _read_u64(handle, file_size)
        metadata_count = _read_u64(handle, file_size)
        if metadata_count > _MAX_METADATA_ENTRIES:
            raise IntegrityError("GGUF metadata count exceeds the supported safety limit.")
        for _ in range(int(metadata_count)):
            key = _read_string(handle, file_size)
            value_type = _read_u32(handle, file_size)
            value = _read_or_skip_gguf_value(handle, value_type, file_size, key in wanted)
            if key in wanted and value is not None:
                captured[key] = value

        maximum_tensor_end = 0
        for _ in range(int(tensor_count)):
            _read_string(handle, file_size)
            dimensions = _read_u32(handle, file_size)
            if dimensions > 16:
                raise IntegrityError("GGUF tensor declares too many dimensions.")
            elements = 1
            for _ in range(dimensions):
                extent = _read_u64(handle, file_size)
                if extent == 0 or elements > (1 << 63) // extent:
                    raise IntegrityError("GGUF tensor dimensions are invalid or overflow the safety bound.")
                elements *= extent
            type_index = _read_u32(handle, file_size)
            tensor_offset = _read_u64(handle, file_size)
            if type_index >= len(_GGML_TYPE_LAYOUT):
                raise IntegrityError(f"Unsupported GGUF tensor type {type_index}.")
            block_size, block_elements = _GGML_TYPE_LAYOUT[type_index]
            encoded_blocks = (elements + block_elements - 1) // block_elements
            maximum_tensor_end = max(maximum_tensor_end, tensor_offset + encoded_blocks * block_size)

        header_end = handle.tell()
        data_start = (header_end + 31) & ~31
        if tensor_count and data_start + maximum_tensor_end > file_size:
            raise IntegrityError("GGUF tensor data is truncated.")

    context_length = next(
        (
            value
            for key, value in captured.items()
            if key.endswith(".context_length") and isinstance(value, int)
        ),
        None,
    )
    return {
        "format": "gguf",
        "gguf_version": version,
        "tensor_count": tensor_count,
        "architecture": captured.get("general.architecture"),
        "name": captured.get("general.name"),
        "description": captured.get("general.description"),
        "file_type": captured.get("general.file_type"),
        "quantization_version": captured.get("general.quantization_version"),
        "context_length": context_length,
    }


def sha256_file(path: Path, block_size: int = _COPY_BLOCK_SIZE) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class ModelStore:
    """Persistent GGUF registry and resumable transfer staging area for one Mac."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or _default_store_root()).expanduser()
        self.models_dir = self.root / "files"
        self.registry_path = self.root / "registry.json"
        self.transfers_path = self.root / "transfers.json"
        self.active_path = self.root / "active.json"
        self._lock = threading.RLock()
        self._ensure_layout()
        self._registry = self._load_json(self.registry_path, {"models": {}})
        self._transfers = self._load_json(self.transfers_path, {"transfers": {}})
        self._active = self._load_json(self.active_path, {"sha256": None})
        self._repair_transfer_offsets()

    def _ensure_layout(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
            os.chmod(self.models_dir, 0o700)
        except OSError:
            pass

    @staticmethod
    def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        if not path.exists():
            return dict(default)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            return loaded if isinstance(loaded, dict) else dict(default)
        except (OSError, json.JSONDecodeError):
            return dict(default)

    def _save(self) -> None:
        _atomic_json_write(self.registry_path, self._registry)
        _atomic_json_write(self.transfers_path, self._transfers)
        _atomic_json_write(self.active_path, self._active)

    def _repair_transfer_offsets(self) -> None:
        changed = False
        for transfer in self._transfers.get("transfers", {}).values():
            part_path = self.models_dir / transfer.get("part_filename", "")
            received = part_path.stat().st_size if part_path.exists() else 0
            if transfer.get("bytes_received") != received:
                transfer["bytes_received"] = received
                transfer["updated_at"] = _now()
                changed = True
        if changed:
            self._save()

    @staticmethod
    def _validate_manifest(filename: str, size_bytes: int, sha256: str) -> Tuple[str, int, str]:
        safe_name = _safe_filename(filename)
        if not isinstance(size_bytes, int) or size_bytes <= 0:
            raise ModelStoreError("Model size_bytes must be a positive integer.")
        normalized_hash = (sha256 or "").lower().strip()
        if not _SHA256_RE.fullmatch(normalized_hash):
            raise ModelStoreError("Model sha256 must be a 64-character hexadecimal digest.")
        return safe_name, size_bytes, normalized_hash

    def _free_space(self) -> int:
        return shutil.disk_usage(self.models_dir).free

    def _ensure_space(self, required_bytes: int) -> None:
        # Reserve an additional 64 MiB to avoid reporting success just before a full disk.
        reserve = 64 * 1024 * 1024
        if self._free_space() < required_bytes + reserve:
            raise InsufficientStorageError(
                f"Insufficient disk space for transfer: need {_format_size(required_bytes)} plus reserve, "
                f"only {_format_size(self._free_space())} free."
            )

    def _record_for_hash(self, digest: str) -> Optional[Dict[str, Any]]:
        return self._registry.get("models", {}).get(digest)

    def _serialize_model(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(record)
        payload["size_formatted"] = _format_size(int(payload["size_bytes"]))
        payload["active"] = payload.get("sha256") == self._active.get("sha256")
        payload["available"] = bool(
            payload.get("availability") == "available"
            and (self.models_dir / payload.get("stored_filename", "")).exists()
        )
        return payload

    def list_models(self) -> List[Dict[str, Any]]:
        with self._lock:
            records = [self._serialize_model(record) for record in self._registry.get("models", {}).values()]
            return sorted(records, key=lambda item: (item["filename"].lower(), item["sha256"]))

    def get_model(self, identifier: str) -> Dict[str, Any]:
        value = (identifier or "").strip()
        with self._lock:
            by_hash = self._record_for_hash(value.lower())
            if by_hash:
                return self._serialize_model(by_hash)
            matches = [
                record
                for record in self._registry.get("models", {}).values()
                if record.get("filename") == value or record.get("stored_filename") == value
            ]
            if len(matches) == 1:
                return self._serialize_model(matches[0])
            if len(matches) > 1:
                raise ModelStoreError("Model filename is ambiguous; select it by SHA-256.")
            raise ModelNotFoundError(f"Model not found: {value}")

    def begin_upload(self, filename: str, size_bytes: int, sha256: str) -> Dict[str, Any]:
        """Create or resume a transfer without buffering model bytes in process memory."""
        safe_name, total_size, digest = self._validate_manifest(filename, size_bytes, sha256)
        with self._lock:
            existing = self._record_for_hash(digest)
            if existing and (self.models_dir / existing.get("stored_filename", "")).exists():
                return {
                    "status": "already_available",
                    "model": self._serialize_model(existing),
                    "transfer": None,
                }

            for transfer in self._transfers.get("transfers", {}).values():
                if transfer.get("sha256") == digest and transfer.get("filename") == safe_name:
                    part_path = self.models_dir / transfer["part_filename"]
                    if transfer.get("status") == "failed":
                        # A failed digest/header check cannot be resumed safely. Preserve no corrupt bytes;
                        # the next explicit retry restarts from zero using the same authenticated manifest.
                        part_path.unlink(missing_ok=True)
                        transfer["bytes_received"] = 0
                        transfer["error"] = None
                        status = "restarted"
                    else:
                        transfer["bytes_received"] = part_path.stat().st_size if part_path.exists() else 0
                        status = "resumed"
                    transfer["status"] = "active"
                    transfer["updated_at"] = _now()
                    self._save()
                    return {"status": status, "model": None, "transfer": self._serialize_transfer(transfer)}
                if transfer.get("filename") == safe_name and transfer.get("sha256") != digest:
                    raise FilenameConflictError(
                        f"An upload is already staging a different model as '{safe_name}'. "
                        "Finish, cancel, or rename that upload first."
                    )

            filename_conflict = [
                record
                for record in self._registry.get("models", {}).values()
                if record.get("filename") == safe_name and record.get("sha256") != digest
            ]
            if filename_conflict:
                raise FilenameConflictError(
                    f"A different model is already stored as '{safe_name}'. Rename the source model before upload."
                )

            self._ensure_space(total_size)
            transfer_id = f"tr_{secrets.token_urlsafe(18)}"
            part_filename = f"{safe_name}.part"
            transfer = {
                "id": transfer_id,
                "filename": safe_name,
                "part_filename": part_filename,
                "size_bytes": total_size,
                "sha256": digest,
                "bytes_received": 0,
                "status": "active",
                "created_at": _now(),
                "updated_at": _now(),
                "error": None,
            }
            self._transfers.setdefault("transfers", {})[transfer_id] = transfer
            self._save()
            return {"status": "created", "model": None, "transfer": self._serialize_transfer(transfer)}

    def _transfer(self, transfer_id: str) -> Dict[str, Any]:
        transfer = self._transfers.get("transfers", {}).get(transfer_id)
        if not transfer:
            raise TransferNotFoundError(f"Transfer not found: {transfer_id}")
        return transfer

    @staticmethod
    def _serialize_transfer(transfer: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(transfer)
        total = int(payload["size_bytes"])
        received = int(payload["bytes_received"])
        payload["progress"] = round((received / total) * 100, 2) if total else 0.0
        return payload

    def get_transfer(self, transfer_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._serialize_transfer(self._transfer(transfer_id))

    def append_chunk(self, transfer_id: str, offset: int, data: bytes) -> Dict[str, Any]:
        """Append a bounded upload chunk at the exact persisted resume offset."""
        if not data:
            raise ModelStoreError("Upload chunk may not be empty.")
        with self._lock:
            transfer = self._transfer(transfer_id)
            if transfer.get("status") != "active":
                raise ModelStoreError(f"Transfer is {transfer.get('status')}; start or resume it before uploading.")
            part_path = self.models_dir / transfer["part_filename"]
            actual_offset = part_path.stat().st_size if part_path.exists() else 0
            if offset != actual_offset:
                raise TransferOffsetError(actual_offset, offset)
            if actual_offset + len(data) > int(transfer["size_bytes"]):
                raise ModelStoreError("Upload chunk exceeds the declared model size.")
            self._ensure_space(len(data))
            with open(part_path, "ab") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            transfer["bytes_received"] = actual_offset + len(data)
            transfer["updated_at"] = _now()
            self._save()
            return self._serialize_transfer(transfer)

    def complete_upload(self, transfer_id: str) -> Dict[str, Any]:
        """Verify and atomically promote a complete staged model into the visible registry."""
        with self._lock:
            transfer = self._transfer(transfer_id)
            part_path = self.models_dir / transfer["part_filename"]
            actual_size = part_path.stat().st_size if part_path.exists() else 0
            expected_size = int(transfer["size_bytes"])
            if actual_size != expected_size:
                transfer["status"] = "incomplete"
                transfer["bytes_received"] = actual_size
                transfer["updated_at"] = _now()
                self._save()
                raise IntegrityError(
                    f"Transfer is incomplete: received {actual_size} of {expected_size} bytes. Resume the upload."
                )

            actual_digest = sha256_file(part_path)
            expected_digest = transfer["sha256"]
            if actual_digest != expected_digest:
                transfer["status"] = "failed"
                transfer["error"] = "SHA-256 mismatch"
                transfer["updated_at"] = _now()
                self._save()
                raise IntegrityError("SHA-256 mismatch. The staged .part file was not promoted.")

            metadata = inspect_gguf(part_path)
            final_path = self.models_dir / transfer["filename"]
            if final_path.exists():
                existing_digest = sha256_file(final_path)
                if existing_digest != expected_digest:
                    raise FilenameConflictError(
                        f"Cannot promote upload: '{transfer['filename']}' already exists with a different SHA-256."
                    )
                part_path.unlink(missing_ok=True)
            else:
                os.replace(part_path, final_path)

            record = {
                "filename": transfer["filename"],
                "stored_filename": final_path.name,
                "path": str(final_path),
                "size_bytes": expected_size,
                "sha256": expected_digest,
                "metadata": metadata,
                "availability": "available",
                "imported_at": _now(),
            }
            self._registry.setdefault("models", {})[expected_digest] = record
            self._transfers.get("transfers", {}).pop(transfer_id, None)
            self._save()
            return self._serialize_model(record)

    def cancel_transfer(self, transfer_id: str) -> Dict[str, Any]:
        """Cancel without deleting the staged bytes, allowing a later manifest to resume safely."""
        with self._lock:
            transfer = self._transfer(transfer_id)
            part_path = self.models_dir / transfer["part_filename"]
            transfer["bytes_received"] = part_path.stat().st_size if part_path.exists() else 0
            transfer["status"] = "cancelled"
            transfer["updated_at"] = _now()
            self._save()
            return self._serialize_transfer(transfer)

    def select_model(self, identifier: str) -> Dict[str, Any]:
        with self._lock:
            model = self.get_model(identifier)
            if not model["available"]:
                raise ModelStoreError("Selected model is not available on disk.")
            self._active["sha256"] = model["sha256"]
            self._active["selected_at"] = _now()
            self._save()
            return self.get_model(model["sha256"])

    def active_model(self) -> Optional[Dict[str, Any]]:
        selected = self._active.get("sha256")
        if not selected:
            return None
        try:
            return self.get_model(str(selected))
        except ModelNotFoundError:
            return None

    def remove_model(self, identifier: str) -> Dict[str, Any]:
        with self._lock:
            model = self.get_model(identifier)
            path = self.models_dir / model["stored_filename"]
            path.unlink(missing_ok=True)
            self._registry.get("models", {}).pop(model["sha256"], None)
            if self._active.get("sha256") == model["sha256"]:
                self._active["sha256"] = None
            self._save()
            return model

    def import_file(self, source: Path) -> Dict[str, Any]:
        """Stream a locally supplied GGUF into the managed store using the same integrity path."""
        source = source.expanduser().resolve()
        if not source.is_file():
            raise ModelStoreError(f"Local source file does not exist: {source}")
        filename = _safe_filename(source.name)
        size_bytes = source.stat().st_size
        digest = sha256_file(source)
        begun = self.begin_upload(filename, size_bytes, digest)
        if begun["status"] == "already_available":
            return begun["model"]
        transfer = begun["transfer"]
        assert transfer is not None
        offset = int(transfer["bytes_received"])
        with open(source, "rb") as handle:
            handle.seek(offset)
            while True:
                block = handle.read(_COPY_BLOCK_SIZE)
                if not block:
                    break
                result = self.append_chunk(transfer["id"], offset, block)
                offset = int(result["bytes_received"])
        return self.complete_upload(transfer["id"])


model_store = ModelStore()
