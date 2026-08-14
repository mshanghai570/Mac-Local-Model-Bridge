"""
CLI Entrypoint and Diagnostic Utilities for Local AI Gateway.
"""
import sys
import argparse
import asyncio
import socket
from typing import List

def run_doctor() -> int:
    """Performs full diagnostics on Python environment, dependencies, Ollama, and network."""
    print("=" * 60)
    print("  Local AI Gateway - Diagnostic Doctor")
    print("=" * 60)

    all_passed = True

    # 1. Check Python version
    py_ver = sys.version_info
    py_ok = (py_ver.major == 3 and py_ver.minor >= 9)
    status_icon = "✓" if py_ok else "✗"
    print(f"[{status_icon}] Python Version: {py_ver.major}.{py_ver.minor}.{py_ver.micro} (>= 3.9 required)")
    if not py_ok:
        all_passed = False

    # 2. Check Dependencies
    deps = [
        ("fastapi", "FastAPI Framework"),
        ("uvicorn", "Uvicorn ASGI Server"),
        ("httpx", "HTTPX Async Client"),
        ("pydantic", "Pydantic Validation"),
        ("zeroconf", "Bonjour Discovery")
    ]
    for mod_name, label in deps:
        try:
            __import__(mod_name)
            print(f"[✓] Dependency '{mod_name}': Installed ({label})")
        except ImportError:
            print(f"[✗] Dependency '{mod_name}': NOT INSTALLED ({label})")
            all_passed = False

    # 3. Check Port Availability
    from .config import config
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_free = False
    try:
        sock.bind((config.host, config.port))
        port_free = True
    except Exception as e:
        port_free = False
    finally:
        sock.close()

    port_icon = "✓" if port_free else "!"
    print(f"[{port_icon}] Gateway Port {config.port}: {'Available' if port_free else 'Port in use or restricted'}")

    # 4. Check Provider Connectivity (Ollama)
    print(f"\nProbing Backend Provider ({config.provider} @ {config.ollama_url})...")
    from .providers import get_provider
    provider = get_provider(config.provider)

    async def probe_provider():
        try:
            health = await provider.check_health()
            if health.provider_status == "connected":
                print(f"[✓] {health.provider_name} status: CONNECTED")
                print(f"    Available models: {health.available_models}")
                
                models = await provider.list_models()
                if models:
                    print("    Installed models on Mac:")
                    for m in models:
                        caps = []
                        if m.capabilities.vision: caps.append("vision")
                        if m.capabilities.tools: caps.append("tools")
                        cap_str = f" [{', '.join(caps)}]" if caps else ""
                        print(f"      - {m.name} ({m.size_formatted}){cap_str}")
                else:
                    print("    [!] Warning: No models installed yet. Run 'ollama pull llama3.2:3b'.")
                return True
            else:
                print(f"[✗] Provider unreachable: {health.message}")
                print("    Remedy: Run 'ollama serve' in your terminal or start the Ollama Mac app.")
                return False
        except Exception as e:
            print(f"[✗] Failed to probe provider: {e}")
            return False

    provider_ok = asyncio.run(probe_provider())
    if not provider_ok:
        all_passed = False

    # 5. Network & Firewall
    auth_desc = "Yes (Bearer token enforced)" if config.is_auth_enabled else "No (Open Local Access - zero-configuration mode)"
    pairing_desc = f"{config.pairing_code} ({'Auto-generated' if config.is_pairing_code_generated else 'Static configured'})"
    print(f"\nLocal Network Configuration:")
    print(f"  LAN Address:   http://{config.lan_ip}:{config.port}")
    print(f"  Localhost:     http://127.0.0.1:{config.port}")
    print(f"  Auth Enabled:  {auth_desc}")
    print(f"  Pairing Code:  {pairing_desc}")

    print("\n" + "=" * 60)
    if all_passed:
        print("  ✓ All diagnostic checks PASSED. Gateway is ready to run.")
        print("  Run 'local-ai-gateway serve' or './start.sh' to launch.")
        return 0
    else:
        print("  ! Some checks failed or require attention. See above for details.")
        return 1

def run_test(prompt: str = "Explain quantum computing in one short sentence.") -> int:
    """Executes a quick live inference completion test."""
    print(f"Running inference test with prompt: '{prompt}'...")
    from .config import config
    from .providers import get_provider
    from .models import ChatRequest, ChatMessage

    provider = get_provider(config.provider)

    async def execute():
        try:
            req = ChatRequest(
                model=config.default_model,
                messages=[ChatMessage(role="user", content=prompt)]
            )
            print(f"Sending to model: {config.default_model}...")
            res = await provider.chat(req)
            print("\nResponse from local model:")
            print("-" * 50)
            print(res.get("content", ""))
            print("-" * 50)
            print("✓ Inference test SUCCESSFUL.")
            return 0
        except Exception as e:
            print(f"✗ Inference test FAILED: {e}")
            return 1

    return asyncio.run(execute())

def cli_entry():
    parser = argparse.ArgumentParser(
        prog="local-ai-gateway",
        description="Local AI Gateway - On-device inference bridge for Apple Silicon, iPhone, and Claude Desktop."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI gateway server")
    serve_parser.add_argument("--port", type=int, help="Port to bind gateway to")
    serve_parser.add_argument("--host", type=str, help="Host to bind gateway to")
    serve_parser.add_argument("--model", type=str, help="Default model name")

    # doctor command
    subparsers.add_parser("doctor", help="Run full environment & connectivity diagnostics")

    # test command
    test_parser = subparsers.add_parser("test", help="Execute a live test completion against local model")
    test_parser.add_argument("--prompt", type=str, default="Write a haiku about Apple Silicon speed.", help="Custom test prompt")

    # mcp command
    subparsers.add_parser("mcp", help="Start the stdio Model Context Protocol (MCP) server for Claude Desktop")

    # version command
    subparsers.add_parser("version", help="Print gateway version information")

    args = parser.parse_args()

    if args.command in (None, "serve", "start"):
        from .config import config
        if getattr(args, "port", None):
            config.port = args.port
        if getattr(args, "host", None):
            config.host = args.host
        if getattr(args, "model", None):
            config.default_model = args.model
        from .server import run_server
        run_server()

    elif args.command == "doctor":
        sys.exit(run_doctor())

    elif args.command == "test":
        sys.exit(run_test(args.prompt))

    elif args.command == "mcp":
        from .mcp.server import start_mcp_server
        start_mcp_server()

    elif args.command == "version":
        print("Local AI Gateway v1.0.0")

if __name__ == "__main__":
    cli_entry()
