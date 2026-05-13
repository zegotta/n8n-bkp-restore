from pathlib import Path
import json

from n8n_backup_restore.models.entities import AppSettings, ServerConfig
from n8n_backup_restore.storage.settings_store import SettingsStore


def test_settings_store_roundtrip(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "config")
    source = AppSettings(
        compare_names_case_sensitive=True,
        publish_created_workflows=True,
        backups_dir="./backups",
        logs_dir="./logs",
        servers=[ServerConfig(alias="hml", instance_url="https://example", api_key="abc")],
    )
    store.save(source)
    restored = store.load()

    assert restored.compare_names_case_sensitive is True
    assert restored.publish_created_workflows is True
    assert len(restored.servers) == 1
    assert restored.servers[0].alias == "hml"
    assert restored.servers[0].instance_url == "https://example"
    assert restored.servers[0].api_key == "abc"


def test_settings_store_load_legacy_server_shape(tmp_path: Path) -> None:
    root = tmp_path / "config"
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "compare_names_case_sensitive": False,
        "backups_dir": "./backups",
        "logs_dir": "./logs",
        "mcp_request_timeout_seconds": 30,
        "servers": [
            {
                "alias": "legacy",
                "url": "https://example.com/mcp-server/http",
                "token": "legacy-token",
            }
        ],
    }
    (root / "settings.json").write_text(json.dumps(payload), encoding="utf-8")
    restored = SettingsStore(root).load()

    assert len(restored.servers) == 1
    assert restored.publish_created_workflows is False
    assert restored.servers[0].alias == "legacy"
    assert restored.servers[0].instance_url == "https://example.com"
    assert restored.servers[0].api_key == "legacy-token"
