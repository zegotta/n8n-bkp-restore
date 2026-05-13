import json
from pathlib import Path

from n8n_backup_restore.models.entities import ServerConfig, WorkflowRecord
from n8n_backup_restore.services.backup_service import BackupService


def test_backup_writes_json_files(tmp_path: Path) -> None:
    service = BackupService(str(tmp_path / "backups"))
    server = ServerConfig(alias="hml", instance_url="http://x", api_key="t")
    target = service.create_backup_dir(server)
    workflows = [
        WorkflowRecord(workflow_id="1", name="Fluxo A", raw={"id": "1", "name": "Fluxo A"}),
        WorkflowRecord(workflow_id="2", name="Fluxo B", raw={"id": "2", "name": "Fluxo B"}),
    ]

    amount = service.save_workflows(target, workflows)
    files = sorted(target.glob("*.json"))

    assert amount == 2
    assert len(files) == 2
    assert json.loads(files[0].read_text(encoding="utf-8"))["name"] in {"Fluxo A", "Fluxo B"}
