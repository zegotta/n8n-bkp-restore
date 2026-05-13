from __future__ import annotations

import itertools
import json
import time
from typing import Any

import httpx

from n8n_backup_restore.models.entities import ServerConfig


class McpError(RuntimeError):
    pass


class McpHttpClient:
    def __init__(self, timeout_seconds: int = 30, max_retries: int = 5, base_retry_delay_seconds: float = 1.0):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.base_retry_delay_seconds = base_retry_delay_seconds
        self._id_counter = itertools.count(1)

    def _post(self, server: ServerConfig, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {server.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = self._post_with_retry(client, server.url, payload, headers)
            data = self._parse_response_payload(response)
        if "error" in data:
            raise McpError(str(data["error"]))
        return data

    def _post_with_retry(
        self,
        client: httpx.Client,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.base_retry_delay_seconds * (2**attempt))
                continue

            if response.status_code == 429:
                if attempt >= self.max_retries:
                    response.raise_for_status()
                wait_seconds = self._retry_wait_seconds(response, attempt)
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            return response

        if last_error is not None:
            raise last_error
        raise McpError("Falha de comunicação com o servidor MCP.")

    def _retry_wait_seconds(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                parsed = float(retry_after)
                if parsed > 0:
                    return parsed
            except ValueError:
                pass

        reset_at = response.headers.get("X-Ratelimit-Reset") or response.headers.get("x-ratelimit-reset")
        if reset_at:
            try:
                wait = float(reset_at) - time.time()
                if wait > 0:
                    return min(wait + 0.25, 60.0)
            except ValueError:
                pass

        return min(self.base_retry_delay_seconds * (2**attempt), 30.0)

    @staticmethod
    def _parse_response_payload(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        text = response.text.strip()

        if not text:
            raise McpError("Resposta MCP vazia do servidor.")

        if "text/event-stream" in content_type:
            for line in text.splitlines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_part = line[5:].strip()
                if not data_part or data_part == "[DONE]":
                    continue
                try:
                    parsed = json.loads(data_part)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
            preview = text[:300]
            raise McpError(f"Resposta SSE MCP sem JSON-RPC válido. Conteúdo: {preview}")

        try:
            parsed = response.json()
        except json.JSONDecodeError:
            preview = text[:300]
            raise McpError(f"Resposta MCP inválida (não JSON). Conteúdo: {preview}") from None

        if not isinstance(parsed, dict):
            raise McpError("Resposta MCP inválida: JSON-RPC esperado em objeto.")
        return parsed

    def _rpc(self, server: ServerConfig, method: str, params: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": next(self._id_counter),
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        result = self._post(server, payload)
        return result.get("result")

    def initialize(self, server: ServerConfig) -> Any:
        return self._rpc(
            server,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "n8n-backup-restore", "version": "0.1.0"},
            },
        )

    def list_tools(self, server: ServerConfig) -> list[dict[str, Any]]:
        result = self._rpc(server, "tools/list", {})
        if not result:
            return []
        return result.get("tools", [])

    def call_tool(self, server: ServerConfig, tool_name: str, arguments: dict[str, Any]) -> Any:
        result = self._rpc(server, "tools/call", {"name": tool_name, "arguments": arguments})
        if isinstance(result, dict) and result.get("isError"):
            message = self._extract_tool_error_message(result) or f"Falha na ferramenta MCP '{tool_name}'."
            raise McpError(message)
        return result

    @staticmethod
    def _extract_tool_error_message(result: dict[str, Any]) -> str | None:
        content = result.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        return None
