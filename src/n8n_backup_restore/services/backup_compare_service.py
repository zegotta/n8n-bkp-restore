from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re


@dataclass(slots=True)
class BackupWorkflow:
    key: str
    name: str
    workflow_id: str
    content_canonical: str
    updated_at_ts: float | None
    comparable_payload: dict


@dataclass(slots=True)
class BackupComparisonRow:
    left_name: str
    left_id: str
    right_name: str
    right_id: str
    status: str


class BackupCompareService:
    def compare_directories(
        self,
        left_dir: Path,
        right_dir: Path,
        include_settings: bool = False,
        include_endpoints: bool = False,
    ) -> list[BackupComparisonRow]:
        same_server = self._is_same_server(left_dir, right_dir)
        left_items = self._load_directory(left_dir, same_server, include_settings, include_endpoints)
        right_items = self._load_directory(right_dir, same_server, include_settings, include_endpoints)
        all_keys = sorted(set(left_items.keys()) | set(right_items.keys()))

        rows: list[BackupComparisonRow] = []
        for key in all_keys:
            left_item = left_items.get(key)
            right_item = right_items.get(key)
            if left_item and right_item:
                if left_item.content_canonical == right_item.content_canonical:
                    status = "Igual"
                else:
                    status = self._different_status(left_item, right_item, same_server)
                rows.append(
                    BackupComparisonRow(
                        left_name=left_item.name,
                        left_id=left_item.workflow_id,
                        right_name=right_item.name,
                        right_id=right_item.workflow_id,
                        status=status,
                    )
                )
                continue
            if left_item:
                rows.append(
                    BackupComparisonRow(
                        left_name=left_item.name,
                        left_id=left_item.workflow_id,
                        right_name="",
                        right_id="",
                        status="Somente A",
                    )
                )
                continue
            if right_item:
                rows.append(
                    BackupComparisonRow(
                        left_name="",
                        left_id="",
                        right_name=right_item.name,
                        right_id=right_item.workflow_id,
                        status="Somente B",
                    )
                )
        return rows

    def _load_directory(
        self,
        backup_dir: Path,
        same_server: bool,
        include_settings: bool,
        include_endpoints: bool,
    ) -> dict[str, BackupWorkflow]:
        items: dict[str, BackupWorkflow] = {}
        for file_path in sorted(backup_dir.glob("*.json")):
            raw = self._read_json(file_path)
            workflow_id = str(raw.get("id") or raw.get("workflowId") or raw.get("workflow_id") or "").strip()
            name = str(raw.get("name") or raw.get("workflowName") or file_path.stem).strip() or file_path.stem
            key = self._workflow_key(workflow_id, name)
            items[key] = BackupWorkflow(
                key=key,
                name=name,
                workflow_id=workflow_id,
                content_canonical=self._canonical_json(
                    raw,
                    same_server,
                    include_settings,
                    include_endpoints,
                ),
                updated_at_ts=self._updated_at_ts(raw),
                comparable_payload=self._build_comparable_payload(
                    raw,
                    same_server,
                    include_settings,
                    include_endpoints,
                ),
            )
        return items

    @staticmethod
    def _workflow_key(workflow_id: str, name: str) -> str:
        # Comparacao entre backups deve considerar somente o nome do fluxo.
        return f"name:{name.strip().lower()}"

    @staticmethod
    def _read_json(file_path: Path) -> dict:
        try:
            parsed = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                return parsed
        except Exception:  # noqa: BLE001
            pass
        return {}

    @staticmethod
    def _canonical_json(
        payload: dict,
        same_server: bool,
        include_settings: bool,
        include_endpoints: bool,
    ) -> str:
        comparable_payload = BackupCompareService._build_comparable_payload(
            payload,
            same_server,
            include_settings,
            include_endpoints,
        )
        return json.dumps(comparable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _build_comparable_payload(
        payload: dict,
        same_server: bool,
        include_settings: bool,
        include_endpoints: bool,
    ) -> dict:
        nodes_raw = payload.get("nodes", [])
        nodes = nodes_raw if isinstance(nodes_raw, list) else []
        if not same_server:
            nodes = [BackupCompareService._normalize_node_for_cross_server(node) for node in nodes]
        if not include_endpoints:
            nodes = [BackupCompareService._normalize_node_without_endpoints(node) for node in nodes]
        nodes = BackupCompareService._sort_nodes_for_compare(nodes)
        settings_value = payload.get("settings", {})
        if not include_settings:
            settings_value = {}
        connections_raw = payload.get("connections", {})
        node_names = {
            str(node.get("name")).strip()
            for node in nodes
            if isinstance(node, dict) and str(node.get("name") or "").strip()
        }
        connections = BackupCompareService._normalize_connections_with_nodes(
            connections_raw,
            node_names=node_names,
            top_level=True,
        )

        comparable_payload = {
            "name": payload.get("name") or payload.get("workflowName"),
            "nodes": nodes,
            "connections": connections,
            "settings": settings_value,
        }
        return comparable_payload

    @staticmethod
    def _updated_at_ts(payload: dict) -> float | None:
        value = payload.get("updatedAt") or payload.get("updated_at")
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.timestamp()

    @staticmethod
    def _different_status(left_item: BackupWorkflow, right_item: BackupWorkflow, same_server: bool) -> str:
        if not same_server:
            return "Diferente"
        left_ts = left_item.updated_at_ts
        right_ts = right_item.updated_at_ts
        if left_ts is not None and right_ts is not None and left_ts != right_ts:
            return "Mais atual em A" if left_ts > right_ts else "Mais atual em B"
        return "Diferente"

    @staticmethod
    def _normalize_node_for_cross_server(node: object) -> object:
        if not isinstance(node, dict):
            return node
        normalized = dict(node)
        normalized.pop("id", None)
        normalized.pop("position", None)
        credentials = normalized.get("credentials")
        if isinstance(credentials, dict):
            clean_credentials: dict[str, object] = {}
            for cred_name, cred_value in credentials.items():
                if isinstance(cred_value, dict):
                    cred_copy = dict(cred_value)
                    cred_copy.pop("id", None)
                    cred_copy.pop("name", None)
                    clean_credentials[cred_name] = cred_copy
                else:
                    clean_credentials[cred_name] = cred_value
            normalized["credentials"] = clean_credentials
        parameters = normalized.get("parameters")
        if isinstance(parameters, dict):
            normalized["parameters"] = BackupCompareService._normalize_parameters_for_cross_server(parameters)
        return normalized

    @staticmethod
    def _normalize_node_without_endpoints(node: object) -> object:
        if not isinstance(node, dict):
            return node
        normalized = dict(node)
        parameters = normalized.get("parameters")
        if isinstance(parameters, dict):
            normalized["parameters"] = BackupCompareService._strip_endpoint_fields(parameters)
        return normalized

    @staticmethod
    def _normalize_parameters_for_cross_server(parameters: dict) -> dict:
        out: dict = {}
        for key, value in parameters.items():
            if key == "id" and {"leftValue", "rightValue", "operator"}.issubset(parameters.keys()):
                # Id interno da regra/condicao na UI do n8n; nao altera a logica.
                continue
            if key == "matchingColumns":
                # Metadata de mapeamento da UI do n8n; nao afeta a logica do workflow.
                continue
            if key == "schema" and isinstance(value, list):
                out[key] = BackupCompareService._normalize_workflow_input_schema_for_cross_server(value)
                continue
            if key == "workflowId":
                if isinstance(value, dict):
                    workflow_ref = dict(value)
                    workflow_ref.pop("value", None)
                    workflow_ref.pop("cachedResultUrl", None)
                    workflow_ref.pop("cachedResultName", None)
                    out[key] = workflow_ref
                else:
                    # Alguns nodes guardam somente o id do subworkflow neste campo.
                    out[key] = None
                continue

            if isinstance(value, dict):
                out[key] = BackupCompareService._normalize_parameters_for_cross_server(value)
            elif isinstance(value, list):
                out[key] = [
                    BackupCompareService._normalize_parameters_for_cross_server(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                out[key] = value
        return out

    @staticmethod
    def _normalize_workflow_input_schema_for_cross_server(schema_items: list[object]) -> list[object]:
        normalized: list[object] = []
        for item in schema_items:
            if not isinstance(item, dict):
                normalized.append(item)
                continue
            if item.get("removed") is True:
                continue
            clean_item = dict(item)
            clean_item.pop("removed", None)
            normalized.append(BackupCompareService._normalize_parameters_for_cross_server(clean_item))
        return normalized

    @staticmethod
    def _sort_nodes_for_compare(nodes: list[object]) -> list[object]:
        def sort_key(node: object) -> tuple[str, str, str]:
            if not isinstance(node, dict):
                return ("", "", json.dumps(node, ensure_ascii=False, sort_keys=True))
            return (
                str(node.get("name") or ""),
                str(node.get("type") or ""),
                json.dumps(node, ensure_ascii=False, sort_keys=True),
            )

        return sorted(nodes, key=sort_key)

    @staticmethod
    def _strip_endpoint_fields(value: object) -> object:
        endpoint_keys = {"url", "endpoint", "baseurl", "apiurl", "webhookurl"}
        if isinstance(value, dict):
            out: dict[str, object] = {}
            for key, item in value.items():
                key_low = str(key).strip().lower()
                if key_low in endpoint_keys:
                    continue
                out[key] = BackupCompareService._strip_endpoint_fields(item)
            return out
        if isinstance(value, list):
            return [BackupCompareService._strip_endpoint_fields(item) for item in value]
        return value

    @staticmethod
    def _is_same_server(left_dir: Path, right_dir: Path) -> bool:
        left_alias = BackupCompareService._extract_backup_alias(left_dir)
        right_alias = BackupCompareService._extract_backup_alias(right_dir)
        if not left_alias or not right_alias:
            return False
        return left_alias == right_alias

    @staticmethod
    def _extract_backup_alias(path: Path) -> str:
        match = re.match(r"^\d{8}_\d{6}_(.+)$", path.name)
        if not match:
            return ""
        return match.group(1).strip().lower()

    def build_workflow_diff_report(
        self,
        left_dir: Path,
        right_dir: Path,
        workflow_name: str,
        include_settings: bool = False,
        include_endpoints: bool = False,
        max_items: int = 200,
    ) -> str:
        same_server = self._is_same_server(left_dir, right_dir)
        left_items = self._load_directory(left_dir, same_server, include_settings, include_endpoints)
        right_items = self._load_directory(right_dir, same_server, include_settings, include_endpoints)
        key = self._workflow_key("", workflow_name)
        left_item = left_items.get(key)
        right_item = right_items.get(key)
        if left_item is None or right_item is None:
            return "Fluxo nao encontrado em ambos os backups selecionados."

        diffs = self._diff_payloads(left_item.comparable_payload, right_item.comparable_payload, max_items=max_items)
        if not diffs:
            return "Sem diferencas no criterio de comparacao atual."

        lines = [
            f"Fluxo: {workflow_name}",
            f"Backup A: {left_dir.name}",
            f"Backup B: {right_dir.name}",
            "",
            f"Diferencas encontradas: {len(diffs)}",
            "",
        ]
        for path, left_value, right_value in diffs:
            left_text = repr(left_value)
            right_text = repr(right_value)
            lines.append(f"- {path}")
            lines.append(f"  A: {left_text}")
            lines.append(f"  B: {right_text}")
            lines.append("")
        return "\n".join(lines).strip()

    def build_workflow_diff_entries(
        self,
        left_dir: Path,
        right_dir: Path,
        workflow_name: str,
        include_settings: bool = False,
        include_endpoints: bool = False,
        max_items: int = 200,
    ) -> list[tuple[str, object, object]]:
        same_server = self._is_same_server(left_dir, right_dir)
        left_items = self._load_directory(left_dir, same_server, include_settings, include_endpoints)
        right_items = self._load_directory(right_dir, same_server, include_settings, include_endpoints)
        key = self._workflow_key("", workflow_name)
        left_item = left_items.get(key)
        right_item = right_items.get(key)
        if left_item is None or right_item is None:
            return [("workflow", "<missing>", "Fluxo nao encontrado em ambos os backups selecionados.")]
        return self._diff_payloads(left_item.comparable_payload, right_item.comparable_payload, max_items=max_items)

    @staticmethod
    def _diff_payloads(left: object, right: object, path: str = "", max_items: int = 200) -> list[tuple[str, object, object]]:
        if max_items <= 0:
            return []
        if type(left) is not type(right):
            return [(path or "<root>", left, right)]
        if isinstance(left, dict):
            out: list[tuple[str, object, object]] = []
            keys = sorted(set(left.keys()) | set(right.keys()))
            for key in keys:
                current_path = f"{path}.{key}" if path else key
                if key not in left:
                    out.append((current_path, "<missing>", right[key]))
                elif key not in right:
                    out.append((current_path, left[key], "<missing>"))
                else:
                    out.extend(
                        BackupCompareService._diff_payloads(
                            left[key],
                            right[key],
                            current_path,
                            max_items=max_items - len(out),
                        )
                    )
                if len(out) >= max_items:
                    return out[:max_items]
            return out
        if isinstance(left, list):
            out: list[tuple[str, object, object]] = []
            if len(left) != len(right):
                out.append((f"{path}.__len__", len(left), len(right)))
                return out
            for idx, (left_item, right_item) in enumerate(zip(left, right)):
                out.extend(
                    BackupCompareService._diff_payloads(
                        left_item,
                        right_item,
                        f"{path}[{idx}]",
                        max_items=max_items - len(out),
                    )
                )
                if len(out) >= max_items:
                    return out[:max_items]
            return out
        if left != right:
            return [(path or "<root>", left, right)]
        return []

    @staticmethod
    def _normalize_connections(value: object) -> object:
        return BackupCompareService._normalize_connections_with_nodes(value)

    @staticmethod
    def _normalize_connections_with_nodes(
        value: object,
        node_names: set[str] | None = None,
        top_level: bool = False,
    ) -> object:
        if isinstance(value, dict):
            normalized_dict: dict[str, object] = {}
            for k, v in value.items():
                if top_level and node_names is not None and str(k) not in node_names:
                    continue
                normalized_value = BackupCompareService._normalize_connections_with_nodes(v, node_names=node_names)
                if normalized_value in ({}, []):
                    continue
                normalized_dict[k] = normalized_value
            return normalized_dict
        if isinstance(value, list):
            normalized_items = [
                BackupCompareService._normalize_connections_with_nodes(item, node_names=node_names) for item in value
            ]
            if node_names is not None:
                normalized_items = [
                    item
                    for item in normalized_items
                    if not (
                        isinstance(item, dict)
                        and set(item.keys()).issubset({"node", "type", "index"})
                        and str(item.get("node") or "") not in node_names
                    )
                ]
            if all(
                isinstance(item, dict)
                and set(item.keys()).issubset({"node", "type", "index"})
                for item in normalized_items
            ):
                return sorted(
                    normalized_items,
                    key=lambda x: (
                        str(x.get("node") or ""),
                        str(x.get("type") or ""),
                        int(x.get("index") or 0),
                    ),
                )
            if all(isinstance(item, list) for item in normalized_items):
                while normalized_items and normalized_items[-1] == []:
                    normalized_items.pop()
            return normalized_items
        return value
