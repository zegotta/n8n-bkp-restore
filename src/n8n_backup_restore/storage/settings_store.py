from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from n8n_backup_restore.models.entities import AppSettings, ServerConfig
from n8n_backup_restore.utils.files import ensure_dir


class SettingsStore:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        ensure_dir(self.root_dir)
        self.file_path = self.root_dir / "settings.json"

    def load(self) -> AppSettings:
        if not self.file_path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        servers = [self._load_server(server) for server in raw.get("servers", [])]
        return AppSettings(
            compare_names_case_sensitive=raw.get("compare_names_case_sensitive", False),
            publish_created_workflows=raw.get("publish_created_workflows", False),
            backups_dir=raw.get("backups_dir", "./backups"),
            logs_dir=raw.get("logs_dir", "./logs"),
            mcp_request_timeout_seconds=raw.get("mcp_request_timeout_seconds", 30),
            servers=servers,
        )

    def save(self, settings: AppSettings) -> None:
        payload = asdict(settings)
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _load_server(server_raw: dict) -> ServerConfig:
        instance_url = str(server_raw.get("instance_url") or server_raw.get("url") or "").strip()
        api_key = str(server_raw.get("api_key") or server_raw.get("token") or "").strip()
        return ServerConfig(
            alias=str(server_raw.get("alias") or "").strip(),
            instance_url=SettingsStore._normalize_instance_url(instance_url),
            api_key=api_key,
        )

    @staticmethod
    def _normalize_instance_url(value: str) -> str:
        url = value.strip().rstrip("/")
        if url.endswith("/mcp-server/http"):
            return url[: -len("/mcp-server/http")]
        return url
