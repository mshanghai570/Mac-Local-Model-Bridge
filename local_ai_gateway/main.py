"""
CLI Entrypoint and Diagnostic Utilities for Local AI Gateway.
"""
import sys
import argparse
import asyncio
import os
import socket
from typing import List

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt
except ImportError:
    Console = None
    Table = None
    Panel = None
    Prompt = None


def _get_console():
    """Get rich console if available, otherwise use print."""
    if Console:
        return Console()
    return None

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
                        if m.capabilities.vision:
                            caps.append("vision")
                        if m.capabilities.tools:
                            caps.append("tools")
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

    firewall_ok = _check_macos_firewall()
    if not firewall_ok:
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("  ✓ All diagnostic checks PASSED. Gateway is ready to run.")
        print("  Run 'local-ai-gateway serve' or './start.sh' to launch.")
        return 0
    else:
        print("  ! Some checks failed or require attention. See above for details.")
        return 1


def _check_macos_firewall() -> bool:
    """Check whether the macOS Application Firewall is enabled and whether python3 is allowed."""
    import shutil
    import subprocess

    socketfilterfw = "/usr/libexec/ApplicationFirewall/socketfilterfw"
    if not os.path.exists(socketfilterfw):
        print("\n[!] macOS Application Firewall status: unable to inspect (command not found).")
        print("    Remedy: open System Settings > Network > Firewall and allow incoming connections for Terminal and python3.")
        return False

    try:
        state = subprocess.check_output([socketfilterfw, "--getglobalstate"], text=True).strip()
    except subprocess.CalledProcessError as e:
        print(f"\n[✗] Failed to query firewall state: {e}")
        return False

    enabled = "enabled" in state.lower()
    print(f"\n[{'✓' if enabled else 'i'}] macOS Firewall: {state}")

    if not enabled:
        return True

    try:
        listing = subprocess.check_output([socketfilterfw, "--listapps"], text=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[✗] Failed to list firewall apps: {e}")
        return False

    python3_allowed = (
        "python3" in listing
        and "Allow" in listing
    )
    if python3_allowed:
        print("  ✓ python3 appears allowed through the firewall.")
        return True

    print("  ✗ python3 is NOT explicitly allowed through the firewall.")
    print("    Remedy: open System Settings > Network > Firewall > Options")
    print("            and allow incoming connections for Terminal (or your shell app) and python3.")
    return False

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

def cmd_models() -> int:
    """List available models with capabilities."""
    console = _get_console()
    from .config import config
    from .providers import get_provider

    provider = get_provider(config.provider)

    async def list_models():
        try:
            models = await provider.list_models()
            if not models:
                if console:
                    console.print("[yellow]No models installed. Run 'ollama pull llama3.2:3b'[/yellow]")
                else:
                    print("[!] No models installed. Run 'ollama pull llama3.2:3b'")
                return 1

            if console and Table:
                table = Table(title="Available Models")
                table.add_column("Name", style="cyan")
                table.add_column("Size", style="magenta")
                table.add_column("Context", style="green")
                table.add_column("Capabilities", style="blue")

                for m in models:
                    caps = []
                    if m.capabilities.vision:
                        caps.append("vision")
                    if m.capabilities.tools:
                        caps.append("tools")
                    cap_str = ", ".join(caps) if caps else "-"
                    table.add_row(
                        m.name,
                        m.size_formatted,
                        f"{m.context_window}",
                        cap_str,
                    )
                console.print(table)
            else:
                print("Available Models:")
                for m in models:
                    caps = []
                    if m.capabilities.vision:
                        caps.append("vision")
                    if m.capabilities.tools:
                        caps.append("tools")
                    cap_str = f" [{', '.join(caps)}]" if caps else ""
                    print(f"  - {m.name} ({m.size_formatted}){cap_str}")
            return 0
        except Exception as e:
            if console:
                console.print(f"[red]Error: {e}[/red]")
            else:
                print(f"Error: {e}")
            return 1

    return asyncio.run(list_models())
 
 
def cmd_config() -> int:
    """Show gateway configuration."""
    console = _get_console()
    from .config import config

    config_text = f"""
[bold]Gateway Configuration[/bold]

[bold]Network:[/bold]
  Host: {config.host}
  Port: {config.port}
  LAN IP: {config.lan_ip}
  URL: http://{config.lan_ip}:{config.port}

[bold]Backend:[/bold]
  Provider: {config.provider}
  Ollama URL: {config.ollama_url}
  Default Model: {config.default_model}

[bold]Features:[/bold]
  Bonjour Discovery: {config.enable_bonjour}
  Pairing Enabled: {config.enable_pairing}
  Dashboard: {config.enable_dashboard}
  Sessions: {config.enable_sessions}
  Auto Routing: {config.enable_auto_routing}

[bold]Security:[/bold]
  Auth Enabled: {config.is_auth_enabled}
  Pairing Code: {config.pairing_code}
"""

    if console and Panel:
        console.print(Panel(config_text, title="[bold]Configuration[/bold]"))
    else:
        print(config_text)
    return 0
 
 
def cmd_pair() -> int:
    """Generate a short-lived pairing code for a nearby iPhone."""
    from .auth import device_manager
    code = device_manager.generate_pairing_code()
    print("Mac Local Model Bridge pairing")
    print(f"  Code: {code}")
    print("  Expires: 5 minutes")
    print(f"  iPhone endpoint: {config.lan_url}")
    print("  Enter the code in Connection → Secure Model Bridge Pairing.")
    return 0


def cmd_stats() -> int:
    """Show gateway statistics and health."""
    console = _get_console()

    config_text = """
[bold]Gateway Statistics[/bold]

[bold]Server Status:[/bold]
  Uptime: N/A
  Active Requests: N/A
  Memory Usage: N/A

[bold]Performance:[/bold]
  Avg TTFT: N/A
  Avg TPS: N/A
  Completed Requests: N/A

Note: Stats collection in progress. Check back after requests are made.
"""

    if console and Panel:
        console.print(Panel(config_text, title="[bold]Statistics[/bold]"))
    else:
        print(config_text)
    return 0
 
 
def cmd_repl() -> int:
    """Start interactive REPL for gateway management."""
    console = _get_console()
    if not console:
        print("REPL requires rich library. Install with: pip install rich")
        return 1

    from .config import config
    from .providers import get_provider

    provider = get_provider(config.provider)

    console.print(
        f"\n[bold cyan]🚀 Local AI Gateway REPL[/bold cyan]\n"
        f"Provider: {config.provider} @ {config.ollama_url}\n"
        f"Default Model: {config.default_model}\n"
        f"Type [bold]/help[/bold] for commands or start managing!\n"
    )

    try:
        while True:
            try:
                user_input = Prompt.ask("[bold cyan]gateway[/bold cyan]")

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    cmd = user_input[1:].split()[0].lower()
                    args = user_input[1:].split()[1:]

                    if cmd in ("exit", "quit"):
                        console.print("[yellow]Goodbye![/yellow]")
                        break
                    elif cmd == "help":
                        show_help()
                    elif cmd == "models":
                        cmd_models()
                    elif cmd == "config":
                        cmd_config()
                    elif cmd == "stats":
                        cmd_stats()
                    elif cmd == "doctor":
                        run_doctor()
                    elif cmd == "test":
                        if args:
                            run_test(" ".join(args))
                        else:
                            run_test()
                    elif cmd == "serve":
                        console.print("[yellow]Gateway is already running. Use Ctrl+C to stop.[/yellow]")
                    else:
                        console.print(f"[red]Unknown command: /{cmd}[/red]")
                else:
                    console.print(f"[yellow]Unknown input: {user_input}[/yellow]")
                    console.print("Type /help for available commands")

            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted. Type /exit to quit.[/yellow]")
                continue

    finally:
        console.print("[yellow]Gateway REPL closed.[/yellow]")

    return 0


def show_help() -> None:
    """Display help menu."""
    help_text = """
[bold cyan]Gateway Management Commands[/bold cyan]

[bold]System[/bold]
  /help           Display this help message
  /exit or /quit  Exit the REPL

[bold]Models[/bold]
  /models         List available models with capabilities

[bold]Configuration[/bold]
  /config         Show current gateway configuration

[bold]Diagnostics[/bold]
  /doctor         Run full environment diagnostics
  /test [prompt]  Test inference with local model

[bold]Server[/bold]
  /serve          Gateway is already running (use Ctrl+C to stop)

[bold]Statistics[/bold]
  /stats          Show gateway performance metrics
"""
    console = _get_console()
    if console and Panel:
        console.print(Panel(help_text, title="[bold]Help[/bold]"))
    else:
        print(help_text)

def cli_entry():
    parser = argparse.ArgumentParser(
        prog="local-ai-gateway",
        description="Local AI Gateway - Mac-hosted local inference bridge for iPhone, Zed, and LAN clients."
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

    # models command
    subparsers.add_parser("models", help="List available models with capabilities")

    # pairing command
    subparsers.add_parser("pair", help="Generate a short-lived iPhone pairing code")

    # config command
    subparsers.add_parser("config", help="Show gateway configuration")

    # stats command
    subparsers.add_parser("stats", help="Show gateway statistics and health")

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

    elif args.command == "models":
        sys.exit(cmd_models())

    elif args.command == "pair":
        sys.exit(cmd_pair())

    elif args.command == "config":
        sys.exit(cmd_config())

    elif args.command == "stats":
        sys.exit(cmd_stats())

    elif args.command == "repl":
        sys.exit(cmd_repl())

    elif args.command == "mcp":
        from .mcp.server import start_mcp_server
        start_mcp_server()

    elif args.command == "version":
        print("Local AI Gateway v1.0.0")

if __name__ == "__main__":
    cli_entry()