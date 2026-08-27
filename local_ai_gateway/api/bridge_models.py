"""Authenticated model-library and llama.cpp runtime routes for iPhone control.

All routes in this module require an *explicitly paired device token*. This is
intentional: it prevents the legacy zero-config open-LAN mode from granting
model upload or process-control authority to any local network peer.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from ..auth import extract_api_key, verify_paired_device_token
from ..model_store import (
    FilenameConflictError,
    InsufficientStorageError,
    IntegrityError,
    ModelNotFoundError,
    ModelStore,
    ModelStoreError,
    TransferNotFoundError,
    TransferOffsetError,
    model_store,
)
from ..runtime import LlamaCppRuntime, RuntimeErrorBase, llama_cpp_runtime

try:
    from fastapi import APIRouter, HTTPException, Request
except ImportError:  # pragma: no cover - FastAPI is a runtime dependency
    APIRouter = None  # type: ignore
    HTTPException = RuntimeError  # type: ignore
    Request = Any  # type: ignore


MAX_UPLOAD_CHUNK_BYTES = int(os.getenv("MAX_UPLOAD_CHUNK_BYTES", str(8 * 1024 * 1024)))


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, TransferOffsetError):
        return HTTPException(
            status_code=409,
            detail={
                "message": str(error),
                "expected_offset": error.expected_offset,
                "received_offset": error.received_offset,
            },
        )
    if isinstance(error, (ModelNotFoundError, TransferNotFoundError)):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, InsufficientStorageError):
        return HTTPException(status_code=507, detail=str(error))
    if isinstance(error, (IntegrityError, ModelStoreError, FilenameConflictError)):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, RuntimeErrorBase):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=500, detail=str(error))


def _parse_offset(request: Request) -> int:
    raw = request.headers.get("x-upload-offset")
    if raw is None:
        range_value = request.headers.get("content-range", "")
        if range_value.startswith("bytes ") and "-" in range_value:
            raw = range_value[6:].split("-", 1)[0]
    if raw is None:
        raise HTTPException(status_code=400, detail="Missing X-Upload-Offset or Content-Range header.")
    try:
        offset = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Upload offset must be an integer.") from exc
    if offset < 0:
        raise HTTPException(status_code=400, detail="Upload offset may not be negative.")
    return offset


def create_bridge_models_router(
    store: ModelStore = model_store,
    runtime: LlamaCppRuntime = llama_cpp_runtime,
    auth_checker: Optional[Callable[[Request], None]] = None,
) -> APIRouter:
    """Create a bridge router, allowing isolated stores/runtimes in tests."""
    if APIRouter is None:  # pragma: no cover
        raise RuntimeError("FastAPI is required to create bridge model routes.")

    router = APIRouter(prefix="/bridge/v1", tags=["iPhone Mac model bridge"])

    def require_paired_device(request: Request) -> None:
        if auth_checker is not None:
            auth_checker(request)
            return
        token = extract_api_key(dict(request.headers), dict(request.query_params))
        if not verify_paired_device_token(token):
            raise HTTPException(
                status_code=401,
                detail="A paired-device token is required for model transfer and runtime control.",
            )

    @router.get("/health")
    async def bridge_health(request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        status = runtime.status()
        return {
            "status": "ok",
            "bridge_protocol_version": "2.0",
            "model_count": len(store.list_models()),
            "active_model": store.active_model(),
            "runtime": status,
        }

    @router.get("/models")
    async def list_bridge_models(request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        models = store.list_models()
        return {"models": models, "count": len(models), "active_model": store.active_model()}

    @router.get("/models/lookup")
    async def lookup_model(sha256: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return {"available": True, "model": store.get_model(sha256)}
        except ModelNotFoundError:
            return {"available": False, "model": None}
        except Exception as exc:
            raise _http_error(exc)

    @router.get("/models/{identifier}")
    async def get_bridge_model(identifier: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return store.get_model(identifier)
        except Exception as exc:
            raise _http_error(exc)

    @router.post("/transfers")
    async def begin_transfer(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return store.begin_upload(
                filename=str(payload.get("filename") or ""),
                size_bytes=payload.get("size_bytes"),
                sha256=str(payload.get("sha256") or ""),
            )
        except Exception as exc:
            raise _http_error(exc)

    @router.get("/transfers/{transfer_id}")
    async def transfer_status(transfer_id: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return store.get_transfer(transfer_id)
        except Exception as exc:
            raise _http_error(exc)

    @router.put("/transfers/{transfer_id}/chunk")
    async def upload_chunk(transfer_id: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_UPLOAD_CHUNK_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload chunks are limited to {MAX_UPLOAD_CHUNK_BYTES} bytes.",
                    )
            except ValueError:
                raise HTTPException(status_code=400, detail="Content-Length must be an integer.")
        body = await request.body()
        if len(body) > MAX_UPLOAD_CHUNK_BYTES:
            raise HTTPException(status_code=413, detail=f"Upload chunks are limited to {MAX_UPLOAD_CHUNK_BYTES} bytes.")
        try:
            return store.append_chunk(transfer_id, _parse_offset(request), body)
        except HTTPException:
            raise
        except Exception as exc:
            raise _http_error(exc)

    @router.post("/transfers/{transfer_id}/complete")
    async def complete_transfer(transfer_id: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return {"model": store.complete_upload(transfer_id)}
        except Exception as exc:
            raise _http_error(exc)

    @router.post("/transfers/{transfer_id}/cancel")
    async def cancel_transfer(transfer_id: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return store.cancel_transfer(transfer_id)
        except Exception as exc:
            raise _http_error(exc)

    @router.post("/models/{identifier}/select")
    async def select_model(identifier: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return {"model": store.select_model(identifier)}
        except Exception as exc:
            raise _http_error(exc)

    @router.delete("/models/{identifier}")
    async def remove_model(identifier: str, request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            model = store.get_model(identifier)
            if runtime.status().get("model_sha256") == model["sha256"]:
                runtime.stop()
            return {"removed": store.remove_model(model["sha256"])}
        except Exception as exc:
            raise _http_error(exc)

    @router.get("/runtime")
    async def runtime_status(request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        return runtime.status()

    @router.post("/runtime/start")
    async def start_runtime(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        identifier = str(payload.get("model") or payload.get("sha256") or "")
        if not identifier:
            selected = store.active_model()
            if not selected:
                raise HTTPException(status_code=400, detail="Select a transferred model before starting the runtime.")
            identifier = str(selected["sha256"])
        try:
            selected = store.select_model(identifier)
            return runtime.start(
                selected["sha256"],
                context_size=payload.get("context_size"),
                threads=payload.get("threads"),
            )
        except Exception as exc:
            raise _http_error(exc)

    @router.post("/runtime/stop")
    async def stop_runtime(request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return runtime.stop()
        except Exception as exc:
            raise _http_error(exc)

    @router.post("/runtime/restart")
    async def restart_runtime(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        require_paired_device(request)
        try:
            return runtime.restart(
                identifier=payload.get("model") or payload.get("sha256"),
                context_size=payload.get("context_size"),
                threads=payload.get("threads"),
            )
        except Exception as exc:
            raise _http_error(exc)

    return router


bridge_models_router = create_bridge_models_router()
