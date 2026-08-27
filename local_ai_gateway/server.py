"""
FastAPI Server Entrypoint and Lifecycle Manager for Local AI Gateway.
"""
import sys
import uuid
import time
import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Optional

from .config import config, ConfigurationError
from .auth import mask_api_key
from .providers import get_provider, close_all_providers
from .discovery.bonjour import BonjourAdvertiser
from .api.rest import router as rest_router
from .api.openai_compat import openai_router
from .api.bridge_models import bridge_models_router
from .web.dashboard import get_dashboard_html
from .errors import GatewayError, format_error_response

# Configure root logging
log_level = logging.DEBUG if config.verbose_logging else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("local_ai_gateway")

try:
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None # type: ignore

bonjour_service: Optional[BonjourAdvertiser] = None
bonjour_thread: Optional[threading.Thread] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Server lifespan lifecycle context managing startup initialization and graceful shutdown.
    """
    global bonjour_service
    # 1. Startup phase
    auth_status_str = "ENABLED (" + mask_api_key(config.api_key) + ")" if config.is_auth_enabled else "DISABLED [Open Local Network Mode]"
    pairing_desc = f"{config.pairing_code} (Auto-generated secure code)" if config.is_pairing_code_generated else f"{config.pairing_code} (Static configured)"

    print("=" * 68)
    print("  Local AI Gateway (Mac Local Inference Bridge)")
    print("=" * 68)
    print(f"  • Gateway Binding:   http://{config.host}:{config.port}")
    print(f"  • Local Loopback:    {config.local_url}")
    print(f"  • LAN IP Address:    {config.lan_url}")
    print(f"  • Model Provider:    {config.provider} ({config.ollama_url})")
    print(f"  • Default Model:     {config.default_model}")
    print(f"  • Authentication:    {auth_status_str}")
    if not config.is_auth_enabled:
        print("                       (To require token auth, set GATEWAY_API_KEY)")
    print(f"  • Pairing Code:      {pairing_desc}")
    print(f"  • Web Dashboard:     {config.lan_url}/")
    print("=" * 68)

    logger.info("Initializing Local AI Gateway...")

    # Start Bonjour / mDNS advertisement
    # Run in a background thread so python-zeroconf spins up its own event loop;
    # calling register_service() on uvicorn's loop would deadlock (EventLoopBlocked).
    if config.enable_bonjour:
        bonjour_service = BonjourAdvertiser(
            port=config.port,
            service_name="Local AI Gateway",
            properties={
                "provider": config.provider,
                "auth_required": bool(config.api_key)
            }
        )
        def _start_bonjour() -> None:
            bonjour_service.start()  # type: ignore[union-attr]
        bonjour_thread = threading.Thread(target=_start_bonjour, name="bonjour-advertiser", daemon=True)
        bonjour_thread.start()

    yield

    # 2. Shutdown phase (SIGINT / SIGTERM)
    logger.info("Initiating graceful gateway shutdown...")
    if bonjour_service:
        bonjour_service.stop()
        bonjour_service = None
    if bonjour_thread and bonjour_thread.is_alive():
        bonjour_thread.join(timeout=5)
        bonjour_thread = None

    await close_all_providers()
    logger.info("Local AI Gateway shutdown complete.")

def create_app() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    if not HAS_FASTAPI:
        raise RuntimeError("FastAPI is not installed. Please run 'pip install fastapi uvicorn'.")

    app = FastAPI(
        title="Local AI Gateway",
        description="On-device AI Gateway bridging iPhone, Claude Desktop, and LAN clients to Apple Silicon LLMs.",
        version="1.0.0",
        lifespan=lifespan
    )

    # 1. CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Request ID & Security Headers Middleware
    @app.middleware("http")
    async def request_lifecycle_middleware(request: Request, call_next):
        req_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:10]}"
        request.state.request_id = req_id
        
        start_time = time.time()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000.0
            logger.error(f"[{req_id}] Unhandled error on {request.method} {request.url.path} ({duration_ms:.1f}ms): {exc}")
            return JSONResponse(
                status_code=500,
                content=format_error_response(f"Internal server error: {str(exc)}", request_id=req_id),
                headers={"X-Request-ID": req_id}
            )

        duration_ms = (time.time() - start_time) * 1000.0
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # 3. Standardized Gateway Error Handler
    @app.exception_handler(GatewayError)
    async def gateway_error_handler(request: Request, exc: GatewayError):
        req_id = getattr(request.state, "request_id", None) or exc.request_id
        return JSONResponse(
            status_code=exc.status_code,
            content=format_error_response(
                message=exc.message,
                error_type=exc.error_type,
                status_code=exc.status_code,
                param=exc.param,
                request_id=req_id
            ),
            headers={"X-Request-ID": req_id} if req_id else None
        )

    # 4. Mount REST and OpenAI Routes
    app.include_router(rest_router)
    app.include_router(openai_router)
    app.include_router(bridge_models_router)

    # 5. Root Dashboard Route
    @app.get("/", response_class=HTMLResponse)
    async def get_dashboard():
        if not config.enable_dashboard:
            return HTMLResponse("<h1>Local AI Gateway is active.</h1>", status_code=200)
        return HTMLResponse(
            get_dashboard_html(
                lan_url=config.lan_url,
                port=config.port,
                has_auth=config.is_auth_enabled,
                default_model=config.default_model,
                pairing_code=config.pairing_code
            )
        )

    return app

def run_server():
    """Starts the Uvicorn ASGI server."""
    try:
        import uvicorn
        config.validate()
        app = create_app()
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            log_level="info" if not config.verbose_logging else "debug",
            access_log=config.verbose_logging
        )
    except ConfigurationError as ce:
        logger.error(f"Configuration Error: {ce}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt. Terminating server.")
    except Exception as e:
        logger.error(f"Fatal server startup error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_server()
