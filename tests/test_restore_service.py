import json
import re
from pathlib import Path

from n8n_backup_restore.models.entities import ServerConfig, WorkflowRecord
from n8n_backup_restore.services.restore_service import RestoreOptions, RestoreService


class FakeWorkflowService:
    def __init__(self, existing: list[WorkflowRecord] | None = None) -> None:
        self.existing = existing or []
        self.created_payloads: list[dict] = []
        self.updated_calls: list[tuple[str, dict]] = []
        self.archived_ids: list[str] = []
        self.activated_ids: list[str] = []

    def list_mcp_enabled_workflows(self, server: ServerConfig) -> list[WorkflowRecord]:
        return self.existing

    def create_workflow(self, server: ServerConfig, payload: dict) -> dict:
        self.created_payloads.append(payload)
        return {"id": f"created-{len(self.created_payloads)}", **payload}

    def update_workflow(self, workflow_id: str, server: ServerConfig, payload: dict) -> dict:
        self.updated_calls.append((workflow_id, payload))
        return payload

    def archive_workflow(self, workflow_id: str, server: ServerConfig) -> dict:
        self.archived_ids.append(workflow_id)
        return {"workflowId": workflow_id, "archived": True}

    def activate_workflow(self, workflow_id: str, server: ServerConfig) -> dict:
        self.activated_ids.append(workflow_id)
        return {"id": workflow_id, "active": True}


def _write_workflow_file(tmp_path: Path, name: str, body: dict) -> Path:
    file_path = tmp_path / f"{name}.json"
    file_path.write_text(json.dumps(body), encoding="utf-8")
    return file_path


def _server() -> ServerConfig:
    return ServerConfig(alias="dev", instance_url="https://n8n.local", api_key="token")


def test_restore_key_case_insensitive() -> None:
    value = RestoreService._key("Meu Fluxo", case_sensitive=False)
    assert value == "meu fluxo"


def test_restore_index_by_name_case_sensitive() -> None:
    items = [WorkflowRecord(workflow_id="1", name="Meu Fluxo", raw={})]
    index = RestoreService._index_by_name(items, case_sensitive=True)
    assert "Meu Fluxo" in index


def test_restore_creates_when_no_conflict(tmp_path: Path) -> None:
    service = FakeWorkflowService(existing=[])
    restore = RestoreService(service)  # type: ignore[arg-type]
    file_path = _write_workflow_file(
        tmp_path,
        "novo_fluxo",
        {
            "name": "Novo Fluxo",
            "nodes": [{"id": "1"}],
            "connections": {},
            "settings": {"executionOrder": "v1"},
            "id": "should-not-be-sent",
        },
    )

    restored, skipped = restore.restore_from_directory(
        _server(),
        tmp_path,
        [file_path],
        RestoreOptions(case_sensitive_name_match=False),
        lambda _name, _wid: True,
    )

    assert restored == 1
    assert skipped == 0
    assert len(service.created_payloads) == 1
    created = service.created_payloads[0]
    assert created["name"] == "Novo Fluxo"
    assert "id" not in created


def test_restore_replaces_conflicting_workflow_with_rename_archive_and_create(tmp_path: Path) -> None:
    existing = [WorkflowRecord(workflow_id="123", name="Fluxo A", raw={})]
    service = FakeWorkflowService(existing=existing)
    restore = RestoreService(service)  # type: ignore[arg-type]
    file_path = _write_workflow_file(
        tmp_path,
        "fluxo_a",
        {
            "name": "Fluxo A",
            "nodes": [{"id": "1"}],
            "connections": {},
        },
    )

    restored, skipped = restore.restore_from_directory(
        _server(),
        tmp_path,
        [file_path],
        RestoreOptions(case_sensitive_name_match=False),
        lambda _name, _wid: True,
    )

    assert restored == 1
    assert skipped == 0
    assert len(service.updated_calls) == 1
    updated_workflow_id, payload = service.updated_calls[0]
    assert updated_workflow_id == "123"
    assert re.match(r"^Fluxo A \(inativo em \d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\)$", payload["name"])
    assert service.archived_ids == ["123"]
    assert len(service.created_payloads) == 1
    assert service.created_payloads[0]["name"] == "Fluxo A"


def test_restore_skips_on_conflict_when_user_declines(tmp_path: Path) -> None:
    existing = [WorkflowRecord(workflow_id="123", name="Fluxo A", raw={})]
    service = FakeWorkflowService(existing=existing)
    restore = RestoreService(service)  # type: ignore[arg-type]
    file_path = _write_workflow_file(
        tmp_path,
        "fluxo_a",
        {"name": "Fluxo A", "nodes": [], "connections": {}},
    )

    restored, skipped = restore.restore_from_directory(
        _server(),
        tmp_path,
        [file_path],
        RestoreOptions(case_sensitive_name_match=False),
        lambda _name, _wid: False,
    )

    assert restored == 0
    assert skipped == 1
    assert service.updated_calls == []
    assert service.archived_ids == []
    assert service.created_payloads == []


def test_build_create_payload_filters_unsupported_settings() -> None:
    payload = RestoreService._build_create_payload(
        {
            "name": "Fluxo",
            "nodes": [],
            "connections": {},
            "settings": {
                "executionOrder": "v1",
                "availableInMCP": True,
                "callerPolicy": "any",
                "timezone": "America/Sao_Paulo",
            },
        }
    )

    assert payload["settings"] == {
        "executionOrder": "v1",
        "timezone": "America/Sao_Paulo",
    }


def test_restore_publishes_created_workflow_when_option_enabled(tmp_path: Path) -> None:
    service = FakeWorkflowService(existing=[])
    restore = RestoreService(service)  # type: ignore[arg-type]
    file_path = _write_workflow_file(
        tmp_path,
        "novo_fluxo_publicado",
        {"name": "Novo Fluxo Publicado", "nodes": [], "connections": {}, "settings": {}},
    )

    restored, skipped = restore.restore_from_directory(
        _server(),
        tmp_path,
        [file_path],
        RestoreOptions(case_sensitive_name_match=False, publish_created_workflows=True),
        lambda _name, _wid: True,
    )

    assert restored == 1
    assert skipped == 0
    assert len(service.created_payloads) == 1
    assert service.activated_ids == ["created-1"]


def test_restore_ignores_publish_error_when_workflow_has_no_trigger(tmp_path: Path) -> None:
    class FakeWorkflowServiceNoTrigger(FakeWorkflowService):
        def activate_workflow(self, workflow_id: str, server: ServerConfig) -> dict:
            raise RuntimeError(
                "Falha ao publicar workflow via API n8n. HTTP 400. Resposta: "
                '{"message":"Workflow cannot be activated because it has no trigger node. '
                'At least one trigger, webhook, or polling node is required."}'
            )

    service = FakeWorkflowServiceNoTrigger(existing=[])
    restore = RestoreService(service)  # type: ignore[arg-type]
    file_path = _write_workflow_file(
        tmp_path,
        "novo_fluxo_sem_trigger",
        {"name": "Novo Fluxo Sem Trigger", "nodes": [], "connections": {}, "settings": {}},
    )

    restored, skipped = restore.restore_from_directory(
        _server(),
        tmp_path,
        [file_path],
        RestoreOptions(case_sensitive_name_match=False, publish_created_workflows=True),
        lambda _name, _wid: True,
    )

    assert restored == 1
    assert skipped == 0
    assert len(service.created_payloads) == 1


def test_restore_reports_progress_callback(tmp_path: Path) -> None:
    service = FakeWorkflowService(existing=[])
    restore = RestoreService(service)  # type: ignore[arg-type]
    file_a = _write_workflow_file(tmp_path, "a", {"name": "A", "nodes": [], "connections": {}, "settings": {}})
    file_b = _write_workflow_file(tmp_path, "b", {"name": "B", "nodes": [], "connections": {}, "settings": {}})
    progress: list[tuple[int, int, str]] = []

    restored, skipped = restore.restore_from_directory(
        _server(),
        tmp_path,
        [file_a, file_b],
        RestoreOptions(case_sensitive_name_match=False),
        lambda _name, _wid: True,
        on_progress=lambda i, t, n: progress.append((i, t, n)),
    )

    assert restored == 2
    assert skipped == 0
    assert progress == [(1, 2, "A"), (2, 2, "B")]
