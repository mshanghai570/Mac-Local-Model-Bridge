#!/usr/bin/env python3
"""
bridge-cli — Mac agent for iPhone-powered local models.

The iPhone runs GGUF inference. This CLI runs on the Mac:

  bridge-cli serve     Mac agent daemon (iPhone discovers it, drives tools)
  bridge-cli chat      Type on the Mac, tokens come from the iPhone
  bridge-cli discover  Find iPhones advertising on-device inference
  bridge-cli "prompt"  One-shot prompt against the iPhone model
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .discovery import discover_iphones, lan_ip
from .session_manager import SessionManager
from .tool_parser import parse_tool_calls, strip_tool_calls
from .tools import ToolExecutor


CONFIG_PATH = Path.home() / ".bridge-cli" / "config.json"
LEGACY_CONFIG_PATH = Path.home() / ".lm_bridge_config.json"

DEFAULT_HOST = os.environ.get("LM_BRIDGE_HOST", "")
DEFAULT_PORT = int(os.environ.get("LM_BRIDGE_PORT", "9090"))
DEFAULT_AGENT_PORT = int(os.environ.get("LM_AGENT_PORT", "8080"))
DEFAULT_MODEL = os.environ.get("LM_BRIDGE_MODEL", "auto")


def load_config() -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "model": DEFAULT_MODEL,
        "api_key": os.environ.get("LM_BRIDGE_API_KEY", ""),
        "phone_url": os.environ.get("LM_PHONE_URL", ""),
    }
    for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                config.update({k: v for k, v in saved.items() if v not in (None, "")})
        except Exception:
            continue
    return config


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
    except OSError:
        pass


def _console():
    try:
        from rich.console import Console

        return Console()
    except ImportError:
        return None


def _print(message: str, style: Optional[str] = None) -> None:
    console = _console()
    if console is None:
        print(message)
        return
    if style:
        console.print(f"[{style}]{message}[/{style}]")
    else:
        console.print(message)


async def _resolve_phone_url(args: argparse.Namespace, config: Dict[str, Any]) -> str:
    if getattr(args, "phone_url", None):
        return str(args.phone_url).rstrip("/")
    if config.get("phone_url"):
        return str(config["phone_url"]).rstrip("/")
    host = getattr(args, "host", None) or config.get("host")
    port = getattr(args, "port", None) or config.get("port") or DEFAULT_PORT
    if host:
        return f"http://{host}:{port}"
    _print("Discovering iPhones on the LAN…")
    found = await asyncio.to_thread(discover_iphones, 2.5)
    if not found:
        raise SystemExit(
            "No iPhone inference server found.\n"
            "Open the iOS app (it advertises on-device GGUF over Bonjour),\n"
            "or pass --phone-url http://IPHONE_LAN_IP:9090"
        )
    if len(found) == 1:
        _print(f"Found {found[0]['name']} at {found[0]['url']}", "green")
        return found[0]["url"]
    _print("Multiple iPhones found:")
    for index, item in enumerate(found, start=1):
        _print(f"  {index}. {item['name']}  {item['url']}")
    return found[0]["url"]


def cmd_serve(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    from .agent_server import serve

    phone_url = args.phone_url or config.get("phone_url") or ""
    if not phone_url and (args.host or config.get("host")):
        host = args.host or config.get("host")
        port = args.port or config.get("port") or DEFAULT_PORT
        phone_url = f"http://{host}:{port}"
    return serve(
        host=args.bind_host,
        port=args.agent_port,
        allow_write=args.allow_write,
        allow_shell=args.allow_shell,
        api_key=args.api_key or config.get("api_key") or "",
        phone_url=phone_url,
    )


def cmd_discover(_args: argparse.Namespace, _config: Dict[str, Any]) -> int:
    _print(f"This Mac LAN IP: {lan_ip()}")
    _print("Scanning for iPhone inference servers (_iphone-inference._tcp)…")
    found = discover_iphones(timeout=3.0)
    if not found:
        _print("None found. Is the iOS app open on the same Wi-Fi?", "yellow")
        return 1
    try:
        from rich.table import Table
        from rich.console import Console

        table = Table(title="iPhone inference servers")
        table.add_column("Name")
        table.add_column("URL")
        for item in found:
            table.add_row(item["name"], item["url"])
        Console().print(table)
    except ImportError:
        for item in found:
            print(f"{item['name']}\t{item['url']}")
    return 0


async def cmd_chat_async(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    from .phone_client import PhoneClient, PhoneClientError
    from .repl_engine import ChatREPL

    phone_url = await _resolve_phone_url(args, config)
    if args.save_config:
        config["phone_url"] = phone_url
        save_config(config)

    parsed = phone_url.replace("http://", "").replace("https://", "")
    host, _, port_s = parsed.partition(":")
    port = int(port_s or DEFAULT_PORT)
    model = args.model or config.get("model") or DEFAULT_MODEL
    api_key = args.api_key or config.get("api_key") or ""
    executor = ToolExecutor(allow_write=args.allow_write, allow_shell=args.allow_shell)

    if args.prompt:
        client = PhoneClient(phone_url, api_key=api_key)
        try:
            messages: List[Dict[str, Any]] = [{"role": "user", "content": args.prompt}]
            for _ in range(6):
                collected = ""
                async for token in client.chat(
                    messages=messages,
                    model=model,
                    temperature=0.7,
                    system=executor.system_prompt(),
                    stream=True,
                ):
                    collected.write(token)
                    sys.stdout.flush()
                    collected += token
                calls = parse_tool_calls(collected)
                if not calls:
                    if not collected.endswith("\n"):
                        sys.stdout.write("\n")
                    return 0
                messages.append({"role": "assistant", "content": collected})
                for call in calls:
                    result = executor.execute(call["name"], call.get("arguments") or {})
                    body = result["content"] if result["ok"] else f"ERROR: {result['error']}"
                    sys.stdout.write(f"\n[mac {call['name']}]\n{body}\n")
                    sys.stdout.flush()
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[Mac tool result — {call['name']}]\n\n{body}",
                        }
                    )
            return 0
        except PhoneClientError as exc:
            _print(str(exc), "red")
            return 1
        finally:
            await client.aclose()

    repl = ChatREPL(
        host=host,
        port=port,
        model=model,
        api_key=api_key,
        session_id=getattr(args, "session", None),
        executor=executor,
        base_url=phone_url,
    )
    await repl.run()
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    console = _console()
    if args.action in (None, "list"):
        sessions = SessionManager.list_sessions()
        if not sessions:
            _print("No saved sessions yet.", "yellow")
            return 0
        if console is None:
            for sess in sessions:
                print(f"{sess['id'][:8]}  {sess['model']}  {sess['message_count']} msgs")
            return 0
        from rich.table import Table

        table = Table(title="Saved Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Updated", style="magenta")
        table.add_column("Model", style="green")
        table.add_column("Messages", style="blue")
        table.add_column("Preview", style="white")
        for sess in sessions:
            table.add_row(
                sess["id"][:8],
                sess["updated_at"][:19],
                sess["model"],
                str(sess["message_count"]),
                (sess.get("preview") or "")[:40],
            )
        console.print(table)
        return 0
    if args.action == "export" and args.session_id:
        export_json = SessionManager.export_session(args.session_id, format="json")
        if not export_json:
            _print(f"Session not found: {args.session_id}", "red")
            return 1
        print(export_json)
        return 0
    if args.action == "delete" and args.session_id:
        if SessionManager.delete_session(args.session_id):
            _print(f"Deleted session: {args.session_id}", "green")
            return 0
        _print(f"Session not found: {args.session_id}", "red")
        return 1
    if args.action == "clear":
        if not args.force:
            _print("Use --force to confirm clearing all sessions", "yellow")
            return 1
        count = SessionManager.clear_all_sessions()
        _print(f"Cleared {count} sessions", "green")
        return 0
    _print("Unknown session action", "red")
    return 1


async def cmd_models_async(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    from .phone_client import PhoneClient, PhoneClientError

    phone_url = await _resolve_phone_url(args, config)
    client = PhoneClient(phone_url, api_key=args.api_key or config.get("api_key") or "")
    try:
        models = await client.list_models()
    except PhoneClientError as exc:
        _print(str(exc), "red")
        return 1
    finally:
        await client.aclose()
    if not models:
        _print("No GGUF models on the iPhone. Import one in the Models tab.", "yellow")
        return 0
    try:
        from rich.table import Table
        from rich.console import Console

        table = Table(title=f"iPhone models @ {phone_url}")
        table.add_column("Name", style="cyan")
        table.add_column("Size", style="magenta")
        for model in models:
            table.add_row(
                str(model.get("name") or model.get("id") or ""),
                str(model.get("size_formatted") or model.get("size") or ""),
            )
        Console().print(table)
    except ImportError:
        for model in models:
            print(model.get("name") or model.get("id"))
    return 0


def cmd_config(args: argparse.Namespace, config: Dict[str, Any]) -> int:
    if args.action in (None, "show"):
        _print(json.dumps({**config, "config_file": str(CONFIG_PATH)}, indent=2))
        return 0
    if args.action == "set" and args.key and args.value is not None:
        value: Any = args.value
        if args.key == "port":
            value = int(args.value)
        config[args.key] = value
        save_config(config)
        _print(f"Set {args.key} = {value}", "green")
        return 0
    if args.action == "reset":
        CONFIG_PATH.unlink(missing_ok=True)
        _print("Configuration reset.", "green")
        return 0
    _print("Unknown config action", "red")
    return 1


def _start_usb_tunnel_if_needed(args: argparse.Namespace) -> Optional[str]:
    """
    If --usb is set, start a USB tunnel and return the phone_url.
    Returns None if --usb was not requested.
    """
    use_usb = getattr(args, "usb", False)
    if not use_usb:
        return None
    from .usb_tunnel import UsbTunnel, find_iphone_usb

    usb_port = getattr(args, "usb_port", DEFAULT_PORT)
    _print(f"Starting USB tunnel to iPhone port {usb_port}…")
    device = find_iphone_usb()
    if device is None:
        raise SystemExit(
            "No iPhone found on USB.\n"
            "Connect your iPhone with a USB cable and tap 'Trust' when prompted."
        )
    _print(f"  Device: {device.get('DeviceName', 'iPhone')} ({device.get('ProductType', '')})", "green")

    tunnel = UsbTunnel(iphone_port=usb_port)
    local_port = tunnel.start()
    _print(f"  Tunnel: 127.0.0.1:{local_port} -> iPhone:{usb_port}", "green")
    # Store tunnel reference so it stays alive for the process lifetime
    import atexit
    atexit.register(tunnel.stop)
    return f"http://127.0.0.1:{local_port}"


def cmd_usb(args: argparse.Namespace) -> int:
    """Show USB tunnel status and connected devices."""
    from .usb_tunnel import list_usb_devices, find_iphone_usb, UsbTunnel

    _print("Scanning USB devices…")
    devices = list_usb_devices()
    if not devices:
        _print("No iOS devices found on USB.", "yellow")
        _print("Connect your iPhone with a USB cable and tap 'Trust' when prompted.")
        return 1

    try:
        from rich.table import Table
        from rich.console import Console

        table = Table(title="USB Devices")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("iOS", style="green")
        table.add_column("Connection", style="blue")
        table.add_column("UDID", style="dim")
        for d in devices:
            table.add_row(
                d.get("DeviceName", "?"),
                d.get("ProductType", "?"),
                d.get("ProductVersion", "?"),
                d.get("ConnectionType", "?"),
                (d.get("UniqueDeviceID") or d.get("Identifier") or "")[:12],
            )
        Console().print(table)
    except ImportError:
        for d in devices:
            conn = d.get("ConnectionType", "?")
            name = d.get("DeviceName", "?")
            print(f"  {name}  ({conn})  {d.get('ProductVersion', '?')}")

    usb_device = find_iphone_usb()
    if usb_device is None:
        _print("\nNo iPhone on USB. (Network devices won't work for USB tunnel.)", "yellow")
        return 1

    usb_port = getattr(args, "port", DEFAULT_PORT)
    _print(f"\nTesting USB tunnel to iPhone port {usb_port}…")
    tunnel = UsbTunnel(iphone_port=usb_port)
    try:
        port = tunnel.start()
        _print(f"  Tunnel active on 127.0.0.1:{port}", "green")
        _print(f"  Try:  bridge-cli chat --usb", "green")
    except RuntimeError as exc:
        _print(f"  {exc}", "red")
        return 1
    finally:
        tunnel.stop()

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bridge-cli",
        description="Mac agent for iPhone-powered local GGUF models.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  bridge-cli serve                     # iPhone-controlled Mac agent\n"
            "  bridge-cli serve --allow-shell       # also allow run_command\n"
            "  bridge-cli chat                      # type on the Mac, model on iPhone\n"
            "  bridge-cli chat --usb                # chat over USB cable\n"
            "  bridge-cli discover                  # find iPhones on Wi-Fi\n"
            "  bridge-cli usb                       # show USB tunnel status\n"
            "  bridge-cli \"summarize ~/notes.md\"    # one-shot\n"
        ),
    )
    parser.add_argument("--host", help="iPhone LAN IP (if not using Bonjour)")
    parser.add_argument("--port", type=int, help="iPhone HTTP port (default 9090)")
    parser.add_argument("--phone-url", help="Full iPhone base URL, e.g. http://192.168.1.20:9090")
    parser.add_argument("--model", help="GGUF filename on the iPhone, or auto")
    parser.add_argument("--api-key", help="Optional shared API key")
    parser.add_argument("--save-config", action="store_true", help="Remember phone URL")
    parser.add_argument("--allow-write", action="store_true", help="Enable write_file")
    parser.add_argument("--allow-shell", action="store_true", help="Enable run_command")
    parser.add_argument(
        "--usb", action="store_true",
        help="Connect to the iPhone over USB cable (requires pymobiledevice3)",
    )
    parser.add_argument(
        "--usb-port", type=int, default=DEFAULT_PORT,
        help="iPhone inference server port when using USB (default 9090)",
    )
    parser.add_argument("prompt", nargs="?", help="One-shot prompt (implies chat)")

    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Run the Mac agent (controlled from the iPhone)")
    serve_p.add_argument("--bind-host", default="0.0.0.0", help="Bind address")
    serve_p.add_argument("--agent-port", type=int, default=DEFAULT_AGENT_PORT, help="Port (default 8080)")
    serve_p.add_argument("--allow-write", action="store_true")
    serve_p.add_argument("--allow-shell", action="store_true")
    serve_p.add_argument("--phone-url", help="Pre-register an iPhone URL")
    serve_p.add_argument("--usb", action="store_true", help="Tunnel to iPhone over USB")
    serve_p.add_argument("--usb-port", type=int, default=DEFAULT_PORT, help="iPhone inference port (default 9090)")

    chat_p = sub.add_parser("chat", help="Interactive chat using the iPhone model")
    chat_p.add_argument("-s", "--session", help="Load a saved session id")
    chat_p.add_argument("--allow-write", action="store_true")
    chat_p.add_argument("--allow-shell", action="store_true")
    chat_p.add_argument("--usb", action="store_true", help="Tunnel to iPhone over USB")
    chat_p.add_argument("--usb-port", type=int, default=DEFAULT_PORT, help="iPhone inference port (default 9090)")

    sub.add_parser("discover", help="Find iPhone inference servers on the LAN")
    sub.add_parser("models", help="List GGUF models installed on the iPhone")

    sessions_p = sub.add_parser("sessions", help="Manage saved chat sessions")
    sessions_p.add_argument("action", nargs="?", choices=["list", "export", "delete", "clear"])
    sessions_p.add_argument("session_id", nargs="?")
    sessions_p.add_argument("--force", action="store_true")

    config_p = sub.add_parser("config", help="Show or set local CLI config")
    config_p.add_argument("action", nargs="?", choices=["show", "set", "reset"])
    config_p.add_argument("key", nargs="?")
    config_p.add_argument("value", nargs="?")

    usb_p = sub.add_parser("usb", help="Show USB tunnel status and connected devices")
    usb_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="iPhone inference port (default 9090)")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config()

    # Global flags are not automatically copied onto subparsers; that's fine.
    try:
        if args.command == "serve":
            # Start USB tunnel if requested, inject phone_url
            usb_url = _start_usb_tunnel_if_needed(args)
            if usb_url:
                setattr(args, "phone_url", usb_url)
            return cmd_serve(args, config)
        if args.command == "discover":
            return cmd_discover(args, config)
        if args.command == "sessions":
            return cmd_sessions(args)
        if args.command == "config":
            return cmd_config(args, config)
        if args.command == "usb":
            return cmd_usb(args)
        if args.command == "models":
            return asyncio.run(cmd_models_async(args, config))
        if args.command == "chat" or args.prompt or args.command is None:
            # Start USB tunnel if requested, inject phone_url
            usb_url = _start_usb_tunnel_if_needed(args)
            if usb_url:
                setattr(args, "phone_url", usb_url)
            return asyncio.run(cmd_chat_async(args, config))
        parser.print_help()
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
