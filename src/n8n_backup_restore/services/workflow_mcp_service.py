from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from n8n_backup_restore.models.entities import ServerConfig, WorkflowRecord
from n8n_backup_restore.services.mcp_client import McpHttpClient


@dataclass(slots=True)
class WorkflowToolContract:
    list_tool: str
    get_tool: str | None
    create_tool: str | None
    update_tool: str | None
    delete_tool: str | None


class WorkflowMcpService:
    _ALLOWED_WORKFLOW_SETTINGS_KEYS = {
        "executionOrder",
        "timezone",
        "errorWorkflow",
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
    }

    def __init__(self, client: McpHttpClient):
        self.client = client

    def test_connection(self, server: ServerConfig) -> tuple[bool, str]:
        try:
            workflows = self._api_list_workflows(server)
            return True, f"Conexao API OK. Total de workflows localizados: {len(workflows)}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def discover_contract(self, server: ServerConfig) -> WorkflowToolContract:
        tools = self.client.list_tools(server)
        names = [str(tool.get("name", "")) for tool in tools]
        indexed = [self._tool_index_entry(tool) for tool in tools]
        names_low = {name.lower(): name for name in names if name}

        preferred_get_tool = self._pick_preferred_name(
            names_low,
            ["get_workflow_details", "workflow_details", "getworkflowdetails"],
        )
        preferred_list_tool = self._pick_preferred_name(
            names_low,
            ["search_workflows", "list_workflows", "get_all_workflows"],
        )

        return WorkflowToolContract(
            list_tool=preferred_list_tool
            or self._pick_tool(
                indexed,
                must_include=["workflow"],
                any_of=[["list"], ["get", "all"], ["search"]],
                must_exclude=["execute", "publish", "unpublish"],
                available_names=names,
            ),
            get_tool=preferred_get_tool
            or self._pick_tool_optional(
                indexed,
                must_include=["workflow"],
                any_of=[["get", "detail"], ["detail"], ["get"], ["read"], ["fetch"]],
                must_exclude=["execute", "publish", "unpublish", "search"],
            ),
            create_tool=self._pick_tool_optional(
                indexed,
                must_include=["workflow"],
                any_of=[["create"], ["insert"]],
                must_exclude=["publish", "unpublish"],
            ),
            update_tool=self._pick_tool_optional(
                indexed, must_include=["workflow"], any_of=[["update"], ["rename"], ["edit"]]
            ),
            delete_tool=self._pick_tool_optional(
                indexed, must_include=["workflow"], any_of=[["delete"], ["remove"]]
            ),
        )

    def list_mcp_enabled_workflows(
        self, server: ServerConfig, contract: WorkflowToolContract | None = None
    ) -> list[WorkflowRecord]:
        items = self._api_list_workflows(server)
        out: list[WorkflowRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            workflow_id = str(
                item.get("id")
                or item.get("workflowId")
                or item.get("workflow_id")
                or item.get("uuid")
                or ""
            )
            name = str(item.get("name") or item.get("workflowName") or item.get("title") or workflow_id)
            out.append(WorkflowRecord(workflow_id=workflow_id, name=name, raw=item))
        return out

    def load_full_workflow(
        self, server: ServerConfig, contract: WorkflowToolContract | None, workflow: WorkflowRecord
    ) -> WorkflowRecord:
        workflow_id = self._resolve_workflow_id(workflow)
        if not workflow_id:
            return workflow
        details = self._api_get_workflow_details(server, workflow_id)
        normalized = details if isinstance(details, dict) else None
        if isinstance(normalized, dict) and normalized:
            return WorkflowRecord(
                workflow_id=str(
                    normalized.get("id")
                    or normalized.get("workflowId")
                    or normalized.get("workflow_id")
                    or workflow.workflow_id
                ),
                name=str(normalized.get("name") or normalized.get("workflowName") or workflow.name),
                raw=normalized,
            )
        return workflow

    def _api_list_workflows(self, server: ServerConfig) -> list[dict[str, Any]]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            while True:
                params: dict[str, Any] = {"limit": 250}
                if cursor:
                    params["cursor"] = cursor
                response = http.get(f"{base}/api/v1/workflows", headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data", []) if isinstance(payload, dict) else []
                if isinstance(data, list):
                    out.extend([item for item in data if isinstance(item, dict)])
                cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
                if not cursor:
                    break
        return out

    def _api_get_workflow_details(self, server: ServerConfig, workflow_id: str) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.get(f"{base}/api/v1/workflows/{workflow_id}", headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Resposta invalida ao carregar detalhes do workflow.")
        return payload

    @staticmethod
    def _api_headers(server: ServerConfig) -> dict[str, str]:
        return {
            "accept": "application/json",
            "X-N8N-API-KEY": server.api_key,
        }

    @staticmethod
    def _resolve_workflow_id(workflow: WorkflowRecord) -> str:
        wid = (workflow.workflow_id or "").strip()
        if wid:
            return wid
        raw = workflow.raw if isinstance(workflow.raw, dict) else {}
        for key in ("id", "workflowId", "workflow_id", "uuid"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _call_list_tool(self, server: ServerConfig, tool_name: str) -> Any:
        # Some MCP servers expose listing as search_* and require a query-ish payload.
        attempts = [{}, {"query": ""}, {"search": ""}, {"term": ""}]
        last_error: Exception | None = None
        for arguments in attempts:
            try:
                return self.client.call_tool(server, tool_name, arguments)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("Falha ao chamar ferramenta de listagem de workflows.")

    def _call_get_tool(self, server: ServerConfig, tool_name: str, workflow_id: str) -> Any:
        attempts = [
            {"workflowId": workflow_id},
            {"id": workflow_id},
            {"workflow_id": workflow_id},
            {"uuid": workflow_id},
        ]
        last_error: Exception | None = None
        last_error_message: str | None = None
        for arguments in attempts:
            try:
                result = self.client.call_tool(server, tool_name, arguments)
                if self._is_tool_error_result(result):
                    last_error_message = self._tool_error_message(result) or "Erro retornado pela ferramenta MCP."
                    continue
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise last_error
        if last_error_message:
            raise RuntimeError(last_error_message)
        raise RuntimeError("Falha ao chamar ferramenta de detalhes de workflow.")

    def create_workflow(self, server: ServerConfig, payload: dict[str, Any]) -> dict[str, Any]:
        return self._api_create_workflow(server, payload)

    def update_workflow(self, workflow_id: str, server: ServerConfig, payload: dict[str, Any]) -> dict[str, Any]:
        return self._api_update_workflow(server, workflow_id, payload)

    def archive_workflow(self, workflow_id: str, server: ServerConfig) -> dict[str, Any]:
        return self._api_archive_workflow(server, workflow_id)

    def activate_workflow(self, workflow_id: str, server: ServerConfig) -> dict[str, Any]:
        return self._api_activate_workflow(server, workflow_id)

    def delete_workflow(self, workflow_id: str, server: ServerConfig) -> bool:
        raise RuntimeError(
            "Operacao de delete desabilitada por seguranca. "
            "Use apenas fluxo de renomear + desativar/arquivar."
        )

    def _api_create_workflow(self, server: ServerConfig, payload: dict[str, Any]) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.post(
                f"{base}/api/v1/workflows",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            )
        self._raise_for_status_with_details(response, "criar workflow")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Resposta invalida ao criar workflow.")
        return data

    def _api_update_workflow(
        self, server: ServerConfig, workflow_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.patch(
                f"{base}/api/v1/workflows/{workflow_id}",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code == 405:
            return self._api_update_workflow_via_put(server, workflow_id, payload)
        self._raise_for_status_with_details(response, "atualizar workflow")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Resposta invalida ao atualizar workflow.")
        return data

    def _api_update_workflow_via_put(
        self, server: ServerConfig, workflow_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        current = self._api_get_workflow_details(server, workflow_id)

        put_payload: dict[str, Any] = {
            "name": str(current.get("name") or ""),
            "nodes": current.get("nodes") if isinstance(current.get("nodes"), list) else [],
            "connections": current.get("connections") if isinstance(current.get("connections"), dict) else {},
            "settings": self._sanitize_workflow_settings(current.get("settings")),
        }
        for key, value in payload.items():
            if key == "settings":
                put_payload[key] = self._sanitize_workflow_settings(value)
                continue
            put_payload[key] = value

        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.put(
                f"{base}/api/v1/workflows/{workflow_id}",
                headers={**headers, "Content-Type": "application/json"},
                json=put_payload,
            )
        self._raise_for_status_with_details(response, "atualizar workflow")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Resposta invalida ao atualizar workflow.")
        return data

    def _api_archive_workflow(self, server: ServerConfig, workflow_id: str) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.post(
                f"{base}/api/v1/workflows/{workflow_id}/archive",
                headers=headers,
                json={},
            )
        if response.status_code == 405:
            return self._api_deactivate_workflow(server, workflow_id)
        self._raise_for_status_with_details(response, "arquivar workflow")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Resposta invalida ao arquivar workflow.")
        return data

    def _api_deactivate_workflow(self, server: ServerConfig, workflow_id: str) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.post(
                f"{base}/api/v1/workflows/{workflow_id}/deactivate",
                headers=headers,
                json={},
            )
        self._raise_for_status_with_details(response, "desativar workflow (fallback do archive)")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Resposta invalida ao desativar workflow.")
        return data

    def _api_activate_workflow(self, server: ServerConfig, workflow_id: str) -> dict[str, Any]:
        base = server.instance_url.rstrip("/")
        headers = self._api_headers(server)
        with httpx.Client(timeout=self.client.timeout_seconds) as http:
            response = http.post(
                f"{base}/api/v1/workflows/{workflow_id}/activate",
                headers=headers,
                json={},
            )
        self._raise_for_status_with_details(response, "publicar workflow")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Resposta invalida ao publicar workflow.")
        return data

    @staticmethod
    def _raise_for_status_with_details(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        detail = response.text.strip()
        if len(detail) > 800:
            detail = detail[:800] + "..."
        raise RuntimeError(
            f"Falha ao {operation} via API n8n. HTTP {response.status_code}. Resposta: {detail or '(vazia)'}"
        )

    @classmethod
    def _sanitize_workflow_settings(cls, settings_raw: Any) -> dict[str, Any]:
        if not isinstance(settings_raw, dict):
            return {}
        return {k: v for k, v in settings_raw.items() if k in cls._ALLOWED_WORKFLOW_SETTINGS_KEYS}

    @staticmethod
    def _extract_items(result: Any) -> list[Any]:
        if not result:
            return []
        structured = result.get("structuredContent") if isinstance(result, dict) else None
        if isinstance(structured, dict):
            for key in ("workflows", "items", "data", "results"):
                value = structured.get(key)
                if isinstance(value, list):
                    return value
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str) and text.strip().startswith("["):
                            import json

                            try:
                                parsed = json.loads(text)
                                if isinstance(parsed, list):
                                    return parsed
                            except Exception:  # noqa: BLE001
                                pass
        return []

    @staticmethod
    def _extract_workflow_payload(result: Any) -> dict[str, Any] | None:
        if isinstance(result, dict):
            structured = result.get("structuredContent")
            if isinstance(structured, dict):
                for key in ("workflow", "item", "data", "result"):
                    value = structured.get(key)
                    if isinstance(value, dict):
                        return value
            for key in ("workflow", "item", "data", "result"):
                value = result.get(key)
                if isinstance(value, dict):
                    return value
            if "id" in result and ("nodes" in result or "connections" in result):
                return result

            content = result.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    text = block.get("text")
                    if not isinstance(text, str):
                        continue
                    text = text.strip()
                    if not text.startswith("{"):
                        continue
                    import json

                    try:
                        parsed = json.loads(text)
                    except Exception:  # noqa: BLE001
                        continue
                    if isinstance(parsed, dict):
                        for key in ("workflow", "item", "data", "result"):
                            nested = parsed.get(key)
                            if isinstance(nested, dict):
                                return nested
                        return parsed
        return None

    @staticmethod
    def _is_tool_error_result(result: Any) -> bool:
        return isinstance(result, dict) and bool(result.get("isError"))

    @staticmethod
    def _tool_error_message(result: Any) -> str | None:
        if not isinstance(result, dict):
            return None
        content = result.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        return None

    @staticmethod
    def _is_mcp_enabled(item: dict[str, Any]) -> bool:
        for key in ("mcpEnabled", "mcp_enabled", "isMcpEnabled", "mcp"):
            value = item.get(key)
            if isinstance(value, bool):
                return value
        return True

    @staticmethod
    def _can_read_details(item: dict[str, Any]) -> bool:
        if item.get("canExecute") is False:
            return False
        scopes = item.get("scopes")
        if isinstance(scopes, list) and scopes:
            as_text = {str(scope) for scope in scopes}
            if "workflow:read" not in as_text:
                return False
        return True

    @staticmethod
    def _pick_tool(
        indexed: list[tuple[str, str]],
        must_include: list[str],
        any_of: list[list[str]],
        must_exclude: list[str] | None = None,
        available_names: list[str] | None = None,
    ) -> str:
        candidates = WorkflowMcpService._score_tools(indexed, must_include, any_of, must_exclude)
        if not candidates:
            available = ", ".join([name for name in (available_names or []) if name])
            raise RuntimeError(
                "Nao foi possivel descobrir o contrato MCP de workflows."
                + (f" Ferramentas disponiveis: {available}" if available else "")
            )
        return candidates[0]

    @staticmethod
    def _pick_tool_optional(
        indexed: list[tuple[str, str]],
        must_include: list[str],
        any_of: list[list[str]],
        must_exclude: list[str] | None = None,
    ) -> str | None:
        candidates = WorkflowMcpService._score_tools(indexed, must_include, any_of, must_exclude)
        return candidates[0] if candidates else None

    @staticmethod
    def _score_tools(
        indexed: list[tuple[str, str]],
        must_include: list[str],
        any_of: list[list[str]],
        must_exclude: list[str] | None = None,
    ) -> list[str]:
        scored: list[tuple[int, str]] = []
        blocked = [w.lower() for w in (must_exclude or [])]
        for name, haystack in indexed:
            if not name:
                continue
            if any(word not in haystack for word in must_include):
                continue
            if any(word in haystack for word in blocked):
                continue
            score = 0
            for group in any_of:
                if all(word in haystack for word in group):
                    score += 10
            if score > 0:
                scored.append((score, name))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [name for _, name in scored]

    @staticmethod
    def _tool_index_entry(tool: dict[str, Any]) -> tuple[str, str]:
        name = str(tool.get("name", ""))
        description = str(tool.get("description", ""))
        haystack = f"{name} {description}".lower()
        return name, haystack

    @staticmethod
    def _pick_preferred_name(names_low: dict[str, str], preferred_tokens: list[str]) -> str | None:
        for token in preferred_tokens:
            token_low = token.lower()
            for low_name, original in names_low.items():
                if token_low in low_name:
                    return original
        return None
