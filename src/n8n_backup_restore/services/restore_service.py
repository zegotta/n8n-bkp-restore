from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from n8n_backup_restore.models.entities import ServerConfig, WorkflowRecord
from n8n_backup_restore.services.workflow_mcp_service import WorkflowMcpService


@dataclass(slots=True)
class RestoreOptions:
    case_sensitive_name_match: bool
    publish_created_workflows: bool = False


class RestoreService:
    def __init__(self, workflow_service: WorkflowMcpService):
        self.workflow_service = workflow_service

    def restore_from_directory(
        self,
        server: ServerConfig,
        backup_dir: str | Path,
        selected_files: list[Path],
        options: RestoreOptions,
        on_conflict_decision: Callable[[str, str], bool],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> tuple[int, int]:
        existing = self.workflow_service.list_mcp_enabled_workflows(server)
        existing_by_name = self._index_by_name(existing, options.case_sensitive_name_match)

        restored = 0
        skipped = 0
        total = len(selected_files)
        for idx, file_path in enumerate(selected_files, start=1):
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            new_name = str(raw.get("name") or raw.get("workflowName") or "workflow_sem_nome")
            current = existing_by_name.get(self._key(new_name, options.case_sensitive_name_match))
            if current:
                replace = on_conflict_decision(new_name, current.workflow_id)
                if not replace:
                    skipped += 1
                    continue
                self._replace_existing(server, current, raw, options)
            else:
                self._create_and_optionally_publish(server, raw, options)
            restored += 1
            if on_progress is not None:
                on_progress(idx, total, new_name)

        return restored, skipped

    def _replace_existing(
        self,
        server: ServerConfig,
        current: WorkflowRecord,
        new_raw: dict,
        options: RestoreOptions,
    ) -> None:
        rename_ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        renamed = f"{current.name} (inativo em {rename_ts})"

        self.workflow_service.update_workflow(current.workflow_id, server, {"name": renamed})
        self.workflow_service.archive_workflow(current.workflow_id, server)
        self._create_and_optionally_publish(server, new_raw, options)

    def _create_and_optionally_publish(
        self,
        server: ServerConfig,
        raw: dict,
        options: RestoreOptions,
    ) -> None:
        created = self.workflow_service.create_workflow(server, self._build_create_payload(raw))
        if not options.publish_created_workflows:
            return
        workflow_id = str(created.get("id") or "").strip() if isinstance(created, dict) else ""
        if not workflow_id:
            raise RuntimeError("Workflow criado sem id retornado pela API; nao foi possivel publicar.")
        try:
            self.workflow_service.activate_workflow(workflow_id, server)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            # Alguns fluxos não podem ser publicados por não possuírem trigger.
            # Nesse caso, mantemos o fluxo criado como inativo e seguimos o restore.
            if "cannot be activated because it has no trigger node" in message or "no trigger node" in message:
                return
            raise

    @staticmethod
    def _build_create_payload(raw: dict) -> dict:
        payload: dict = {}

        name = raw.get("name") or raw.get("workflowName") or "workflow_sem_nome"
        payload["name"] = str(name)
        payload["nodes"] = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
        payload["connections"] = raw.get("connections") if isinstance(raw.get("connections"), dict) else {}
        payload["settings"] = RestoreService._sanitize_settings(raw.get("settings"))

        return payload

    @staticmethod
    def _sanitize_settings(settings_raw: object) -> dict:
        if not isinstance(settings_raw, dict):
            return {}

        allowed_keys = {
            "executionOrder",
            "timezone",
            "errorWorkflow",
            "saveExecutionProgress",
            "saveManualExecutions",
            "saveDataErrorExecution",
            "saveDataSuccessExecution",
            "executionTimeout",
        }
        return {key: value for key, value in settings_raw.items() if key in allowed_keys}

    @staticmethod
    def _index_by_name(items: list[WorkflowRecord], case_sensitive: bool) -> dict[str, WorkflowRecord]:
        return {RestoreService._key(item.name, case_sensitive): item for item in items}

    @staticmethod
    def _key(value: str, case_sensitive: bool) -> str:
        return value if case_sensitive else value.lower()
