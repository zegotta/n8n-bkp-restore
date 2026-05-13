from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ServerConfig:
    alias: str
    instance_url: str
    api_key: str

    @property
    def url(self) -> str:
        # Legacy compatibility while backup/restore still uses MCP transport.
        return f"{self.instance_url.rstrip('/')}/mcp-server/http"

    @property
    def token(self) -> str:
        # Legacy compatibility while backup/restore still uses MCP transport.
        return self.api_key


@dataclass(slots=True)
class AppSettings:
    compare_names_case_sensitive: bool = False
    publish_created_workflows: bool = False
    backups_dir: str = "./backups"
    logs_dir: str = "./logs"
    mcp_request_timeout_seconds: int = 30
    servers: list[ServerConfig] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowRecord:
    workflow_id: str
    name: str
    raw: dict[str, Any]
