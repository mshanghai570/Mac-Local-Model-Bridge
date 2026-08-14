"""
Performance telemetry, TTFT, TPS, and concurrency tracking for Local AI Gateway.
"""
import time
import asyncio
import threading
from typing import Dict, List, Optional, Any
from collections import deque
from .models import RequestMetric
from .config import config

class MetricsCollector:
    """
    In-memory performance metrics tracker and concurrency limiter.
    """
    def __init__(self, max_history: int = 100):
        self._metrics_history: deque = deque(maxlen=max_history)
        self._active_requests: Dict[str, RequestMetric] = {}
        self._lock = threading.RLock()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._boot_time = time.time()
        self._total_requests_count = 0
        self._total_tokens_streamed = 0

    def get_semaphore(self) -> asyncio.Semaphore:
        """Lazily instantiates the asyncio semaphore in the active event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        return self._semaphore

    def start_request(self, request_id: str, model: str, endpoint: str) -> RequestMetric:
        with self._lock:
            self._total_requests_count += 1
            metric = RequestMetric(
                request_id=request_id,
                model=model,
                endpoint=endpoint,
                start_time=time.time(),
                success=True,
                cancelled=False
            )
            self._active_requests[request_id] = metric
            return metric

    def record_first_token(self, request_id: str) -> None:
        with self._lock:
            metric = self._active_requests.get(request_id)
            if metric and metric.ttft_ms is None:
                metric.ttft_ms = (time.time() - metric.start_time) * 1000.0

    def finish_request(
        self,
        request_id: str,
        completion_tokens: int = 0,
        prompt_tokens: Optional[int] = None,
        success: bool = True,
        cancelled: bool = False,
        error_message: Optional[str] = None
    ) -> Optional[RequestMetric]:
        with self._lock:
            metric = self._active_requests.pop(request_id, None)
            if not metric:
                return None

            now = time.time()
            duration_s = max(0.001, now - metric.start_time)
            metric.total_duration_ms = duration_s * 1000.0
            metric.completion_tokens = completion_tokens
            metric.prompt_tokens = prompt_tokens
            metric.success = success and not cancelled
            metric.cancelled = cancelled
            metric.error_message = error_message

            if completion_tokens > 0:
                self._total_tokens_streamed += completion_tokens
                metric.tokens_per_second = completion_tokens / duration_s

            self._metrics_history.append(metric)
            return metric

    def get_active_count(self) -> int:
        with self._lock:
            return len(self._active_requests)

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            history = list(self._metrics_history)
            completed_count = len(history)
            avg_ttft = 0.0
            avg_tps = 0.0

            valid_ttfts = [m.ttft_ms for m in history if m.ttft_ms is not None]
            if valid_ttfts:
                avg_ttft = sum(valid_ttfts) / len(valid_ttfts)

            valid_tps = [m.tokens_per_second for m in history if m.tokens_per_second is not None and m.tokens_per_second > 0]
            if valid_tps:
                avg_tps = sum(valid_tps) / len(valid_tps)

            system_info = self._get_system_resources()

            return {
                "uptime_seconds": round(time.time() - self._boot_time, 1),
                "total_requests": self._total_requests_count,
                "active_requests": len(self._active_requests),
                "max_concurrent_limit": config.max_concurrent_requests,
                "completed_requests": completed_count,
                "total_tokens_streamed": self._total_tokens_streamed,
                "avg_ttft_ms": round(avg_ttft, 2),
                "avg_tokens_per_sec": round(avg_tps, 2),
                "system_resources": system_info
            }

    def get_recent_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            history = list(self._metrics_history)
            return [m.to_dict() for m in reversed(history[-limit:])]

    def _get_system_resources(self) -> Dict[str, Any]:
        """Collects basic host CPU and RAM metrics."""
        resources: Dict[str, Any] = {
            "platform": "Apple Silicon / macOS",
            "available_ram_gb": None,
            "total_ram_gb": None,
            "cpu_percent": None
        }
        try:
            import psutil
            mem = psutil.virtual_memory()
            resources["available_ram_gb"] = round(mem.available / (1024 ** 3), 2)
            resources["total_ram_gb"] = round(mem.total / (1024 ** 3), 2)
            resources["cpu_percent"] = psutil.cpu_percent(interval=None)
        except Exception:
            pass
        return resources

metrics_collector = MetricsCollector()
