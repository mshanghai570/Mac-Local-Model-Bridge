"""Loopback-only llama.cpp runtime supervisor for the Mac model bridge.

This module starts an externally installed llama.cpp server against a verified
GGUF held by :mod:`local_ai_gateway.model_store`. It does not download, compile,
or embed an inference engine. The server is deliberately bound to 127.0.0.1 so
LAN access remains mediated by the authenticated gateway.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover - dependency declared by project
    httpx = None  # type: ignore

try:
    import psutil
except ImportError:  # pragma: no cover - dependency declared by project
    psutil = None  # type: ignore

from ..model_store import ModelNotFoundError, ModelStore, model_store


class RuntimeErrorBase(Exception):
    """Base error for llama.cpp runtime lifecycle operations."""


class RuntimeUnavailableError(RuntimeErrorBase):
    """Raised when a llama.cpp server executable is unavailable."""


class RuntimeStartError(RuntimeErrorBase):
    """Raised when a launched server exits or fails its readiness check."""


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value >= minimum else default
    except ValueError:
        return default


class LlamaCppRuntime:
    """Manage one local, CPU-first llama.cpp HTTP server process."""

    def __init__(
        self,
        store: ModelStore = model_store,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        executable: Optional[str] = None,
        startup_timeout: float = 20.0,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("llama.cpp runtime must bind to loopback only.")
        self.store = store
        self.host = host
        self.port = port or _int_env("LLAMA_SERVER_PORT", 8081)
        self.executable_override = executable or os.getenv("LLAMA_SERVER_PATH", "").strip() or None
        self.startup_timeout = startup_timeout
        self._lock = threading.RLock()
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._model_sha256: Optional[str] = None
        self._started_at: Optional[float] = None
        self._log_path: Optional[Path] = None
        self._last_error: Optional[str] = None
        self._command: Optional[List[str]] = None

    @property
    def base_url(self) -> str:
        host = "127.0.0.1" if self.host == "localhost" else self.host
        return f"http://{host}:{self.port}"

    def _resolve_executable(self) -> Tuple[str, List[str]]:
        """Return executable plus any mandatory command prefix such as ``serve``."""
        candidates: List[str] = []
        if self.executable_override:
            candidates.append(self.executable_override)
        candidates.extend(["llama-server", "llama"])
        for candidate in candidates:
            resolved = candidate if os.path.isabs(candidate) else shutil.which(candidate)
            if not resolved or not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
                continue
            prefix = [resolved]
            if Path(resolved).name == "llama":
                prefix.append("serve")
            return resolved, prefix
        requested = self.executable_override or "llama-server (or llama serve)"
        raise RuntimeUnavailableError(
            f"llama.cpp executable not found: {requested}. Install a current x86_64 llama.cpp build "
            "or set LLAMA_SERVER_PATH to its llama-server/llama binary."
        )

    def _log_file(self) -> Path:
        logs = self.store.root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(logs, 0o700)
        except OSError:
            pass
        return logs / "llama-server.log"

    def _is_port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex(("127.0.0.1", self.port)) == 0

    def _wait_until_ready(self, process: subprocess.Popen[bytes]) -> None:
        deadline = time.monotonic() + self.startup_timeout
        last_error = "runtime did not report readiness"
        while time.monotonic() < deadline:
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeStartError(self._startup_error(f"llama.cpp exited with code {return_code}"))
            if httpx is not None:
                try:
                    response = httpx.get(f"{self.base_url}/health", timeout=0.5)
                    if 200 <= response.status_code < 500:
                        return
                except Exception as exc:  # normal while process starts
                    last_error = str(exc)
            elif self._is_port_open():
                return
            time.sleep(0.15)
        raise RuntimeStartError(self._startup_error(f"Timed out waiting for {self.base_url}/health: {last_error}"))

    def _startup_error(self, prefix: str) -> str:
        tail = ""
        if self._log_path and self._log_path.exists():
            try:
                with open(self._log_path, "rb") as handle:
                    handle.seek(max(0, self._log_path.stat().st_size - 8192))
                    tail = handle.read().decode("utf-8", errors="replace").strip()
            except OSError:
                tail = ""
        if tail:
            return f"{prefix}. llama.cpp log tail: {tail[-2000:]}"
        return prefix

    def _build_command(
        self,
        prefix: Sequence[str],
        model_path: Path,
        context_size: Optional[int],
        threads: Optional[int],
        api_key: Optional[str],
    ) -> List[str]:
        command = list(prefix) + [
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--gpu-layers",
            "0",  # Intel CPU-first default; callers may deliberately launch another runtime separately.
        ]
        if context_size:
            command.extend(["--ctx-size", str(context_size)])
        if threads:
            command.extend(["--threads", str(threads)])
        if api_key:
            command.extend(["--api-key", api_key])
        return command

    def start(
        self,
        identifier: str,
        context_size: Optional[int] = None,
        threads: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start the verified selected model and wait for the loopback server to be ready."""
        with self._lock:
            model = self.store.get_model(identifier)
            if not model.get("available"):
                raise ModelNotFoundError(f"Model is not available on disk: {identifier}")
            model_path = Path(str(model["path"]))
            if not model_path.is_file():
                raise ModelNotFoundError(f"Model file no longer exists: {model_path}")

            existing = self.status()
            if existing["running"]:
                if existing.get("model_sha256") == model["sha256"]:
                    return existing
                self.stop()

            _, prefix = self._resolve_executable()
            if self._is_port_open():
                raise RuntimeStartError(
                    f"Port {self.port} is already in use on loopback. Stop the conflicting process or set LLAMA_SERVER_PORT."
                )
            command = self._build_command(prefix, model_path, context_size, threads, api_key)
            log_path = self._log_file()
            with open(log_path, "wb") as log_handle:
                try:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        close_fds=True,
                    )
                except OSError as exc:
                    raise RuntimeStartError(f"Failed to launch llama.cpp: {exc}") from exc

            self._process = process
            self._model_sha256 = str(model["sha256"])
            self._started_at = time.time()
            self._log_path = log_path
            self._last_error = None
            self._command = command
            try:
                self._wait_until_ready(process)
            except Exception as exc:
                self._last_error = str(exc)
                self.stop()
                raise
            return self.status()

    def stop(self) -> Dict[str, Any]:
        """Stop the managed process; no unrelated process is ever terminated."""
        with self._lock:
            process = self._process
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=4)
            self._process = None
            self._model_sha256 = None
            self._started_at = None
            self._command = None
            return self.status()

    def restart(
        self,
        identifier: Optional[str] = None,
        context_size: Optional[int] = None,
        threads: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = identifier or self._model_sha256
        if not target:
            active = self.store.active_model()
            if not active:
                raise ModelNotFoundError("No active model selected. Select a transferred GGUF before starting.")
            target = str(active["sha256"])
        self.stop()
        return self.start(target, context_size=context_size, threads=threads, api_key=api_key)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            process = self._process
            running = bool(process and process.poll() is None)
            pid = process.pid if running and process else None
            memory_bytes: Optional[int] = None
            if running and pid and psutil is not None:
                try:
                    memory_bytes = int(psutil.Process(pid).memory_info().rss)
                except Exception:
                    memory_bytes = None
            active_model = self.store.active_model()
            running_model: Optional[Dict[str, Any]] = None
            if self._model_sha256:
                try:
                    running_model = self.store.get_model(self._model_sha256)
                except ModelNotFoundError:
                    running_model = None
            return {
                "runtime": "llama.cpp",
                "host": "127.0.0.1",
                "port": self.port,
                "base_url": self.base_url,
                "running": running,
                "pid": pid,
                "model_sha256": self._model_sha256 if running else None,
                "model": running_model,
                "selected_model": active_model,
                "started_at": self._started_at if running else None,
                "memory_bytes": memory_bytes,
                "cpu_first": True,
                "hardware": platform.machine(),
                "log_path": str(self._log_path) if self._log_path else None,
                "last_error": self._last_error,
                "command": self._command if running else None,
            }


llama_cpp_runtime = LlamaCppRuntime()
