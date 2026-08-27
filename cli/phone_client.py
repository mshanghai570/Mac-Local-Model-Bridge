"""
HTTP client for the iPhone on-device inference server (PhoneHttpServer).
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


class PhoneClientError(Exception):
    pass


class PhoneClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _client_obj(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> Dict[str, Any]:
        client = await self._client_obj()
        try:
            response = await client.get(f"{self.base_url}/health", headers=self._headers())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise PhoneClientError(f"iPhone health check failed at {self.base_url}: {exc}") from exc

    async def list_models(self) -> List[Dict[str, Any]]:
        client = await self._client_obj()
        for path in ("/models", "/v1/models"):
            try:
                response = await client.get(f"{self.base_url}{path}", headers=self._headers())
                if response.status_code != 200:
                    continue
                payload = response.json()
                if isinstance(payload, dict) and "models" in payload:
                    return list(payload.get("models") or [])
                if isinstance(payload, dict) and "data" in payload:
                    return [
                        {"name": item.get("id"), "model": item.get("id")}
                        for item in payload.get("data") or []
                    ]
            except httpx.HTTPError:
                continue
        return []

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = "auto",
        temperature: float = 0.7,
        system: Optional[str] = None,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        """Yield content tokens from the iPhone. Completes when the stream ends."""
        client = await self._client_obj()
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        url = f"{self.base_url}/v1/chat/completions"
        headers = self._headers()
        if stream:
            headers["Accept"] = "text/event-stream"

        try:
            if stream:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise PhoneClientError(
                            f"iPhone inference HTTP {response.status_code}: {body[:500]}"
                        )
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        token = _extract_token(chunk)
                        if token:
                            yield token
            else:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code >= 400:
                    raise PhoneClientError(
                        f"iPhone inference HTTP {response.status_code}: {response.text[:500]}"
                    )
                data = response.json()
                content = _extract_completion_text(data)
                if content:
                    yield content
        except PhoneClientError:
            raise
        except httpx.HTTPError as exc:
            raise PhoneClientError(f"cannot reach iPhone at {self.base_url}: {exc}") from exc


def _extract_token(chunk: Dict[str, Any]) -> str:
    if "content" in chunk and isinstance(chunk.get("content"), str):
        return chunk["content"] or ""
    choices = chunk.get("choices") or []
    if choices:
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if isinstance(content, str):
            return content
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _extract_completion_text(data: Dict[str, Any]) -> str:
    if isinstance(data.get("content"), str):
        return data["content"]
    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""
