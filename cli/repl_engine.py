"""
Interactive REPL that talks to the iPhone inference server and runs Mac tools.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from .phone_client import PhoneClient, PhoneClientError
from .session_manager import Message, Session, SessionManager
from .tool_parser import parse_tool_calls, strip_tool_calls
from .tools import ToolExecutor


class ChatREPL:
    def __init__(
        self,
        host: str,
        port: int,
        model: str = "auto",
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        executor: Optional[ToolExecutor] = None,
        base_url: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.model = model
        self.api_key = api_key or ""
        self.base_url = (base_url or f"http://{host}:{port}").rstrip("/")
        self.console = Console()
        self.executor = executor or ToolExecutor()
        if session_id:
            self.session = SessionManager.load(session_id) or self._create_new_session()
        else:
            self.session = self._create_new_session()
        self.client = PhoneClient(self.base_url, api_key=self.api_key)

    def _create_new_session(self) -> Session:
        return Session.create(
            session_id=str(uuid4())[:8],
            model=self.model,
            host=self.host,
            port=self.port,
            metadata={"auto_save": True, "phone_url": self.base_url},
        )

    def _history_payload(self) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for msg in self.session.messages:
            if not msg.content:
                continue
            payload.append({"role": msg.role, "content": msg.content})
        return payload

    async def chat_once(self, user_input: str) -> None:
        self.session.add_message(Message(role="user", content=user_input))
        for _ in range(6):
            collected = ""
            try:
                async for token in self.client.chat(
                    messages=self._history_payload(),
                    model=self.session.model,
                    system=self.executor.system_prompt(),
                    stream=True,
                ):
                    collected += token
                    self.console.print(token, end="", highlight=False)
            except PhoneClientError as exc:
                self.console.print(f"\n[red]{exc}[/red]")
                return
            self.console.print()
            calls = parse_tool_calls(collected)
            visible = strip_tool_calls(collected)
            self.session.add_message(Message(role="assistant", content=collected))
            self.session.save()
            if not calls:
                if visible != collected:
                    # already printed raw including tags; that's acceptable
                    pass
                return
            for call in calls:
                self.console.print(f"[yellow]mac tool {call['name']}[/yellow] {call.get('arguments')}")
                result = self.executor.execute(call["name"], call.get("arguments") or {})
                body = result["content"] if result["ok"] else f"ERROR: {result['error']}"
                preview = body if len(body) < 800 else body[:800] + "\n…[truncated]"
                self.console.print(f"[dim]{preview}[/dim]")
                self.session.add_message(
                    Message(
                        role="tool",
                        content=body,
                    )
                )
                self.session.add_message(
                    Message(
                        role="user",
                        content=f"[Mac tool result — {call['name']}]\n\n{body}",
                    )
                )
            self.session.save()

    def show_help(self) -> None:
        self.console.print(
            Panel(
                """
[bold]Chat[/bold]
  type normally          Send a prompt to the iPhone model
  /models                List GGUF files on the iPhone
  /switch <file.gguf>    Use a different on-device model
  /clear                 Reset conversation
  /history               Show messages
  /sessions              List saved sessions
  /load <id>             Resume a session
  /export                Dump this session as JSON
  /settings              Show endpoint + tools
  /exit                  Quit
""",
                title="bridge-cli",
            )
        )

    def show_settings(self) -> None:
        self.console.print(
            Panel(
                f"""
[bold]iPhone:[/bold] {self.base_url}
[bold]Model:[/bold] {self.session.model}
[bold]Session:[/bold] {self.session.id}
[bold]Tools:[/bold] {', '.join(self.executor.available_names())}
""",
                title="Settings",
            )
        )

    def show_history(self) -> None:
        if not self.session.messages:
            self.console.print("[yellow]No messages yet.[/yellow]")
            return
        for msg in self.session.messages:
            if msg.role == "user" and msg.content and msg.content.startswith("[Mac tool result"):
                continue
            label = {"user": "You", "assistant": "iPhone", "tool": "Mac tool"}.get(msg.role, msg.role)
            self.console.print(f"[bold]{label}:[/bold] {(msg.content or '')[:400]}")

    def show_sessions(self) -> None:
        sessions = SessionManager.list_sessions()
        if not sessions:
            self.console.print("[yellow]No saved sessions yet.[/yellow]")
            return
        table = Table(title="Saved Sessions")
        table.add_column("ID")
        table.add_column("Model")
        table.add_column("Messages")
        for sess in sessions:
            table.add_row(sess["id"][:8], sess["model"], str(sess["message_count"]))
        self.console.print(table)

    async def run(self) -> None:
        self.console.print(
            f"\n[bold cyan]bridge-cli[/bold cyan]  iPhone {self.base_url}  model={self.session.model}\n"
            "Type /help for commands. Tokens stream from the iPhone; tools run here.\n"
        )
        try:
            while True:
                try:
                    user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
                except (EOFError, KeyboardInterrupt):
                    self.console.print("\n[yellow]Goodbye.[/yellow]")
                    break
                if not user_input.strip():
                    continue
                if user_input.startswith("/"):
                    bits = user_input[1:].split()
                    cmd = bits[0].lower()
                    rest = bits[1:]
                    if cmd in {"exit", "quit"}:
                        break
                    if cmd == "help":
                        self.show_help()
                    elif cmd == "settings":
                        self.show_settings()
                    elif cmd == "history":
                        self.show_history()
                    elif cmd == "sessions":
                        self.show_sessions()
                    elif cmd == "clear":
                        self.session.messages = []
                        self.session.save()
                        self.console.print("[yellow]Cleared.[/yellow]")
                    elif cmd == "switch" and rest:
                        self.session.model = rest[0]
                        self.console.print(f"[yellow]Model set to {rest[0]}[/yellow]")
                    elif cmd == "load" and rest:
                        loaded = SessionManager.load(rest[0])
                        if loaded:
                            self.session = loaded
                            self.console.print(f"[yellow]Loaded {rest[0]}[/yellow]")
                        else:
                            self.console.print("[red]Session not found[/red]")
                    elif cmd == "export":
                        blob = SessionManager.export_session(self.session.id, format="json")
                        if blob:
                            self.console.print(Panel(Syntax(blob, "json", theme="monokai")))
                    elif cmd == "models":
                        try:
                            models = await self.client.list_models()
                        except PhoneClientError as exc:
                            self.console.print(f"[red]{exc}[/red]")
                            continue
                        if not models:
                            self.console.print("[yellow]No GGUF models on the iPhone.[/yellow]")
                        for model in models:
                            self.console.print(f"  {model.get('name') or model.get('id')}")
                    else:
                        self.console.print(f"[red]Unknown command /{cmd}[/red]")
                    continue
                await self.chat_once(user_input)
        finally:
            await self.client.aclose()
            self.session.save()

    async def run_once(self, prompt: str) -> int:
        try:
            await self.chat_once(prompt)
            return 0
        except Exception as exc:  # noqa: BLE001
            self.console.print(f"[red]{exc}[/red]")
            return 1
        finally:
            await self.client.aclose()
