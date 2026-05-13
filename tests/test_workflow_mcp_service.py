from n8n_backup_restore.services.workflow_mcp_service import WorkflowMcpService


def test_sanitize_workflow_settings_filters_unsupported_keys() -> None:
    result = WorkflowMcpService._sanitize_workflow_settings(
        {
            "executionOrder": "v1",
            "timezone": "America/Sao_Paulo",
            "availableInMCP": True,
            "callerPolicy": "workflowsFromSameOwner",
        }
    )

    assert result == {
        "executionOrder": "v1",
        "timezone": "America/Sao_Paulo",
    }
