from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from n8n_backup_restore.services.mcp_client import McpHttpClient
from n8n_backup_restore.services.restore_service import RestoreService
from n8n_backup_restore.services.workflow_mcp_service import WorkflowMcpService
from n8n_backup_restore.storage.settings_store import SettingsStore
from n8n_backup_restore.ui.main_window import MainWindow
from n8n_backup_restore.utils.logging_setup import build_logger


def main() -> int:
    project_root = Path.cwd()
    settings_store = SettingsStore(project_root / "config")
    settings = settings_store.load()
    logger = build_logger(settings.logs_dir)
    logger.info("Aplicação iniciada.")

    app = QApplication(sys.argv)
    client = McpHttpClient(timeout_seconds=settings.mcp_request_timeout_seconds)
    workflow_service = WorkflowMcpService(client)
    restore_service = RestoreService(workflow_service)
    window = MainWindow(settings_store, workflow_service, restore_service, logger)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
