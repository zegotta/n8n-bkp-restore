from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from n8n_backup_restore.models.entities import ServerConfig, WorkflowRecord
from n8n_backup_restore.utils.files import ensure_dir, sanitize_filename


class BackupService:
    def __init__(self, backups_dir: str):
        self.backups_dir = backups_dir

    def create_backup_dir(self, server: ServerConfig) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{stamp}_{sanitize_filename(server.alias)}"
        root = ensure_dir(self.backups_dir)
        target = root / folder_name
        target.mkdir(parents=True, exist_ok=False)
        return target

    def save_workflows(self, target_dir: Path, workflows: Iterable[WorkflowRecord]) -> int:
        count = 0
        for workflow in workflows:
            file_name = f"{sanitize_filename(workflow.name)}_{sanitize_filename(workflow.workflow_id)}.json"
            file_path = target_dir / file_name
            file_path.write_text(
                json.dumps(workflow.raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            count += 1
        return count
