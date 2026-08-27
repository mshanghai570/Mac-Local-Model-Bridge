#!/usr/bin/env python3
"""Local Mac CLI for the verified GGUF model store and llama.cpp runtime."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

import httpx

from local_ai_gateway.model_store import ModelStoreError, model_store
from local_ai_gateway.runtime import RuntimeErrorBase, llama_cpp_runtime


def _runtime_key(args: argparse.Namespace) -> str:
    return str(getattr(args, "runtime_api_key", "") or os.getenv("LLAMA_SERVER_API_KEY", ""))


def _print(payload: Any, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, default=str)}")
            else:
                print(f"{key}: {value}")
        return
    print(payload)


def _runtime_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def cmd_status(args: argparse.Namespace) -> int:
    status = llama_cpp_runtime.status()
    status["model_count"] = len(model_store.list_models())
    _print(status, args.json)
    return 0 if status["running"] else 1


def cmd_models(args: argparse.Namespace) -> int:
    models = model_store.list_models()
    if args.json:
        _print({"models": models, "count": len(models)}, True)
        return 0
    if not models:
        print("No GGUF models in the Mac bridge store.")
        return 0
    print("Available Mac GGUF models:")
    for model in models:
        selected = "*" if model.get("active") else " "
        print(f"{selected} {model['filename']}  {model['size_formatted']}  sha256:{model['sha256'][:12]}")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    model = model_store.import_file(args.model)
    _print({"imported": model}, args.json)
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    selected = model_store.select_model(args.model)
    _print({"selected": selected}, args.json)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    identifier = args.model
    if identifier:
        model_store.select_model(identifier)
    else:
        active = model_store.active_model()
        if not active:
            raise ModelStoreError("No active model. Run `bridge select <model>` or pass a model to `bridge start`.")
        identifier = active["sha256"]
    status = llama_cpp_runtime.start(
        identifier,
        context_size=args.context_size,
        threads=args.threads,
        api_key=_runtime_key(args) or None,
    )
    _print(status, args.json)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    _print(llama_cpp_runtime.stop(), args.json)
    return 0


def _stream_chat(prompt: str, temperature: float, max_tokens: Optional[int], api_key: str) -> Iterable[str]:
    status = llama_cpp_runtime.status()
    if not status.get("running"):
        raise RuntimeErrorBase("llama.cpp runtime is not running. Run `bridge start` first.")
    model = status.get("model") or model_store.active_model()
    if not model:
        raise ModelStoreError("No active model is selected.")
    payload: Dict[str, Any] = {
        "model": model["filename"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    with httpx.stream(
        "POST",
        f"{status['base_url']}/v1/chat/completions",
        headers=_runtime_headers(api_key),
        json=payload,
        timeout=httpx.Timeout(connect=5, read=600, write=30, pool=5),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                return
            try:
                message = json.loads(data)
                choice = (message.get("choices") or [{}])[0]
                content = (choice.get("delta") or {}).get("content")
                if content:
                    yield str(content)
            except (json.JSONDecodeError, AttributeError, IndexError):
                continue


def cmd_run(args: argparse.Namespace) -> int:
    wrote = False
    for token in _stream_chat(args.prompt, args.temperature, args.max_tokens, _runtime_key(args)):
        sys.stdout.write(token)
        sys.stdout.flush()
        wrote = True
    if wrote:
        sys.stdout.write("\n")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    print("Mac bridge chat. Type /exit to quit.")
    while True:
        try:
            prompt = input("bridge> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt in {"/exit", "/quit"}:
            return 0
        if not prompt:
            continue
        try:
            for token in _stream_chat(prompt, args.temperature, args.max_tokens, _runtime_key(args)):
                sys.stdout.write(token)
                sys.stdout.flush()
            print()
        except (httpx.HTTPError, ModelStoreError, RuntimeErrorBase) as exc:
            print(f"error: {exc}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bridge",
        description="Manage Mac-stored GGUF models and a loopback-only Intel llama.cpp runtime.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--runtime-api-key", help="llama.cpp API key, if the runtime was started with one.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show bridge model and runtime status.")
    subparsers.add_parser("models", help="List verified GGUF models on this Mac.")

    upload = subparsers.add_parser("upload", help="Import a local GGUF file into the Mac model store.")
    upload.add_argument("model", help="Path to a local .gguf file.")

    select = subparsers.add_parser("select", help="Select a stored model by filename or SHA-256.")
    select.add_argument("model")

    start = subparsers.add_parser("start", help="Start loopback llama.cpp against a selected model.")
    start.add_argument("model", nargs="?", help="Stored filename or SHA-256; defaults to active selection.")
    start.add_argument("--context-size", type=int, help="Context size passed to llama.cpp.")
    start.add_argument("--threads", type=int, help="CPU threads passed to llama.cpp.")

    subparsers.add_parser("stop", help="Stop only the llama.cpp process started by this CLI/gateway.")

    for command in ("run", "chat"):
        target = subparsers.add_parser(command, help="Stream a prompt response" if command == "run" else "Start an interactive streamed chat")
        target.add_argument("--temperature", type=float, default=0.7)
        target.add_argument("--max-tokens", type=int)
        if command == "run":
            target.add_argument("prompt")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "status": cmd_status,
        "models": cmd_models,
        "upload": cmd_upload,
        "select": cmd_select,
        "start": cmd_start,
        "stop": cmd_stop,
        "run": cmd_run,
        "chat": cmd_chat,
    }
    try:
        return handlers[args.command](args)
    except (ModelStoreError, RuntimeErrorBase, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
