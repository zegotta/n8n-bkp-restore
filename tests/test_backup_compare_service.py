from __future__ import annotations

import json
from pathlib import Path

from n8n_backup_restore.services.backup_compare_service import BackupCompareService


def _write_workflow(path: Path, workflow_id: str, name: str, extra: dict | None = None) -> None:
    payload = {"id": workflow_id, "name": name}
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_compare_detects_equal_and_different_and_missing(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-a"
    left.mkdir()
    right.mkdir()

    _write_workflow(left / "a.json", "1", "Fluxo A", {"nodes": [{"id": "x"}]})
    _write_workflow(left / "b.json", "2", "Fluxo B", {"nodes": [{"id": "left"}], "updatedAt": "2026-05-21T10:00:00Z"})
    _write_workflow(left / "c.json", "3", "Fluxo C", {"nodes": []})

    _write_workflow(right / "a.json", "1", "Fluxo A", {"nodes": [{"id": "x"}]})
    _write_workflow(right / "b.json", "2", "Fluxo B", {"nodes": [{"id": "right"}], "updatedAt": "2026-05-20T10:00:00Z"})
    _write_workflow(right / "d.json", "4", "Fluxo D", {"nodes": []})

    service = BackupCompareService()
    rows = service.compare_directories(left, right)
    statuses = {(row.left_name or row.right_name, row.status) for row in rows}

    assert ("Fluxo A", "Igual") in statuses
    assert ("Fluxo B", "Mais atual em A") in statuses
    assert ("Fluxo C", "Somente A") in statuses
    assert ("Fluxo D", "Somente B") in statuses


def test_compare_matches_by_name_when_id_is_missing(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    (left / "x.json").write_text(json.dumps({"name": "Fluxo Sem ID", "value": 1}), encoding="utf-8")
    (right / "y.json").write_text(json.dumps({"name": "Fluxo Sem ID", "value": 1}), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_ignores_id_and_matches_by_name_only(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    _write_workflow(left / "x.json", "AAA", "Fluxo Nome Unico", {"nodes": [{"id": "n1"}]})
    _write_workflow(right / "y.json", "BBB", "Fluxo Nome Unico", {"nodes": [{"id": "n1"}]})

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"
    assert rows[0].left_id == "AAA"
    assert rows[0].right_id == "BBB"


def test_compare_orders_rows_alphabetically_by_name(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    _write_workflow(left / "z.json", "1", "fluxoZ")
    _write_workflow(right / "a.json", "2", "fluxoA")
    _write_workflow(left / "m.json", "3", "fluxoM")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)
    names = [row.left_name or row.right_name for row in rows]

    assert names == ["fluxoA", "fluxoM", "fluxoZ"]


def test_compare_cross_server_ignores_node_id_position_credentials_id_and_updated_at(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    left_payload = {
        "id": "A1",
        "name": "Fluxo X",
        "updatedAt": "2026-05-10T10:00:00Z",
        "nodes": [
            {
                "id": "node-a",
                "name": "N1",
                "type": "n8n-nodes-base.set",
                "position": [100, 100],
                "credentials": {"postgres": {"id": "cred-a", "name": "PG"}},
            }
        ],
        "connections": {},
        "settings": {},
    }
    right_payload = {
        "id": "B1",
        "name": "Fluxo X",
        "updatedAt": "2026-05-21T10:00:00Z",
        "nodes": [
            {
                "id": "node-b",
                "name": "N1",
                "type": "n8n-nodes-base.set",
                "position": [999, 999],
                "credentials": {"postgres": {"id": "cred-b", "name": "PG"}},
            }
        ],
        "connections": {},
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_cross_server_ignores_workflow_reference_ids_and_credential_name(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    left_payload = {
        "name": "wf_files_08_index_create",
        "nodes": [
            {
                "id": "node-a",
                "name": "Execute Workflow",
                "type": "n8n-nodes-base.executeWorkflow",
                "position": [100, 100],
                "parameters": {
                    "workflowId": {
                        "mode": "list",
                        "value": "AAA111",
                        "cachedResultUrl": "/workflow/AAA111",
                        "cachedResultName": "subflow-a",
                    }
                },
            },
            {
                "id": "node-b",
                "name": "OpenAI",
                "type": "n8n-nodes-base.openAi",
                "credentials": {"openAiApi": {"id": "cred-a", "name": "OpenAI DEV"}},
            },
        ],
        "connections": {},
        "settings": {},
    }

    right_payload = {
        "name": "wf_files_08_index_create",
        "nodes": [
            {
                "id": "node-x",
                "name": "Execute Workflow",
                "type": "n8n-nodes-base.executeWorkflow",
                "position": [999, 999],
                "parameters": {
                    "workflowId": {
                        "mode": "list",
                        "value": "BBB222",
                        "cachedResultUrl": "/workflow/BBB222",
                        "cachedResultName": "subflow-b",
                    }
                },
            },
            {
                "id": "node-y",
                "name": "OpenAI",
                "type": "n8n-nodes-base.openAi",
                "credentials": {"openAiApi": {"id": "cred-b", "name": "OpenAI PROD"}},
            },
        ],
        "connections": {},
        "settings": {},
    }

    (left / "x.json").write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_cross_server_ignores_execute_workflow_matching_columns(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    left_payload = {
        "name": "schedule_users_in_groups",
        "nodes": [
            {
                "name": "List groups",
                "type": "n8n-nodes-base.executeWorkflow",
                "parameters": {
                    "workflowId": {
                        "mode": "list",
                        "value": "AAA111",
                        "cachedResultUrl": "/workflow/AAA111",
                        "cachedResultName": "fn_zapster_list_groups",
                    },
                    "workflowInputs": {
                        "matchingColumns": [
                            "zapster_instance_id_firstItem_firstItem",
                            "id_lastItem",
                            "zapster_token_firstItem_firstItem",
                        ],
                        "value": {},
                    },
                },
            }
        ],
        "connections": {},
        "settings": {},
    }
    right_payload = {
        "name": "schedule_users_in_groups",
        "nodes": [
            {
                "name": "List groups",
                "type": "n8n-nodes-base.executeWorkflow",
                "parameters": {
                    "workflowId": {
                        "mode": "list",
                        "value": "BBB222",
                        "cachedResultUrl": "/workflow/BBB222",
                        "cachedResultName": "fn_zapster_list_groups",
                    },
                    "workflowInputs": {
                        "matchingColumns": [],
                        "value": {},
                    },
                },
            }
        ],
        "connections": {},
        "settings": {},
    }

    (left / "x.json").write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_cross_server_ignores_removed_fields_in_workflow_input_schema(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    left_payload = {
        "name": "Vitoria - individual chat",
        "nodes": [
            {
                "name": "Log response",
                "type": "n8n-nodes-base.executeWorkflow",
                "parameters": {
                    "workflowInputs": {
                        "schema": [
                            {
                                "id": "message_text",
                                "displayName": "message_text",
                                "type": "string",
                                "removed": False,
                            },
                            {
                                "id": "message_media_original_filename",
                                "displayName": "message_media_original_filename",
                                "type": "string",
                                "removed": True,
                            },
                        ],
                        "value": {"message_text": "ok"},
                    }
                },
            }
        ],
        "connections": {},
        "settings": {},
    }
    right_payload = {
        "name": "Vitoria - individual chat",
        "nodes": [
            {
                "name": "Log response",
                "type": "n8n-nodes-base.executeWorkflow",
                "parameters": {
                    "workflowInputs": {
                        "schema": [
                            {
                                "id": "message_text",
                                "displayName": "message_text",
                                "type": "string",
                            }
                        ],
                        "value": {"message_text": "ok"},
                    }
                },
            }
        ],
        "connections": {},
        "settings": {},
    }

    (left / "x.json").write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_cross_server_ignores_condition_ids_in_switch_rules(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    left_payload = {
        "name": "fn_get_file_sharepoint",
        "nodes": [
            {
                "name": "Switch",
                "type": "n8n-nodes-base.switch",
                "parameters": {
                    "rules": {
                        "values": [
                            {
                                "conditions": {
                                    "conditions": [
                                        {
                                            "id": "dev-rule-id",
                                            "leftValue": "={{ $json.type }}",
                                            "rightValue": "unprocessed_file",
                                            "operator": {"type": "string", "operation": "equals"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
            }
        ],
        "connections": {},
        "settings": {},
    }
    right_payload = {
        "name": "fn_get_file_sharepoint",
        "nodes": [
            {
                "name": "Switch",
                "type": "n8n-nodes-base.switch",
                "parameters": {
                    "rules": {
                        "values": [
                            {
                                "conditions": {
                                    "conditions": [
                                        {
                                            "id": "prd-rule-id",
                                            "leftValue": "={{ $json.type }}",
                                            "rightValue": "unprocessed_file",
                                            "operator": {"type": "string", "operation": "equals"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                },
            }
        ],
        "connections": {},
        "settings": {},
    }

    (left / "x.json").write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_same_server_can_toggle_settings_comparison(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-a"
    left.mkdir()
    right.mkdir()

    base = {
        "id": "1",
        "name": "Fluxo Settings",
        "nodes": [{"name": "N1", "type": "n8n-nodes-base.set"}],
        "connections": {},
    }
    payload_a = {**base, "settings": {"timezone": "America/Sao_Paulo"}}
    payload_b = {**base, "settings": {"timezone": "UTC"}}
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows_without_settings = service.compare_directories(left, right, include_settings=False)
    rows_with_settings = service.compare_directories(left, right, include_settings=True)

    assert len(rows_without_settings) == 1
    assert rows_without_settings[0].status == "Igual"
    assert len(rows_with_settings) == 1
    assert rows_with_settings[0].status == "Diferente"


def test_compare_cross_server_respects_settings_checkbox(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    base = {
        "id": "1",
        "name": "Fluxo Settings Cross",
        "nodes": [{"name": "N1", "type": "n8n-nodes-base.set"}],
        "connections": {},
    }
    payload_a = {**base, "settings": {"timezone": "America/Sao_Paulo"}}
    payload_b = {**base, "settings": {"timezone": "UTC"}}
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows_without_settings = service.compare_directories(left, right, include_settings=False)
    rows_with_settings = service.compare_directories(left, right, include_settings=True)

    assert len(rows_without_settings) == 1
    assert rows_without_settings[0].status == "Igual"
    assert len(rows_with_settings) == 1
    assert rows_with_settings[0].status == "Diferente"


def test_compare_ignores_workflow_description(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "Fluxo Desc",
        "description": None,
        "nodes": [{"name": "N1", "type": "n8n-nodes-base.set"}],
        "connections": {},
        "settings": {},
    }
    payload_b = {
        "name": "Fluxo Desc",
        "description": "Descricao diferente",
        "nodes": [{"name": "N1", "type": "n8n-nodes-base.set"}],
        "connections": {},
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right, include_settings=False)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_ignores_connections_order(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "Fluxo Conexao",
        "nodes": [{"name": "create case", "type": "n8n-nodes-base.set"}],
        "connections": {
            "create case": {
                "main": [
                    [
                        {"node": "Get monitors", "type": "main", "index": 0},
                        {"node": "Create a conversation", "type": "main", "index": 0},
                        {"node": "Create folder at agent sharepoint", "type": "main", "index": 0},
                    ]
                ]
            }
        },
        "settings": {},
    }
    payload_b = {
        "name": "Fluxo Conexao",
        "nodes": [{"name": "create case", "type": "n8n-nodes-base.set"}],
        "connections": {
            "create case": {
                "main": [
                    [
                        {"node": "Create a conversation", "type": "main", "index": 0},
                        {"node": "Create folder at agent sharepoint", "type": "main", "index": 0},
                        {"node": "Get monitors", "type": "main", "index": 0},
                    ]
                ]
            }
        },
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right, include_settings=False)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_ignores_trailing_empty_connection_branches(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "Fluxo Branch",
        "nodes": [{"name": "Is Last Chunk?", "type": "n8n-nodes-base.if"}],
        "connections": {
            "Is Last Chunk?": {
                "main": [
                    [{"node": "Update", "type": "main", "index": 0}],
                    [],
                ]
            }
        },
        "settings": {},
    }
    payload_b = {
        "name": "Fluxo Branch",
        "nodes": [{"name": "Is Last Chunk?", "type": "n8n-nodes-base.if"}],
        "connections": {
            "Is Last Chunk?": {
                "main": [
                    [{"node": "Update", "type": "main", "index": 0}],
                ]
            }
        },
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right, include_settings=False)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_ignores_empty_error_connection_block_vs_missing(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "wf_files_06_chunk_division",
        "nodes": [{"name": "Publish files", "type": "n8n-nodes-base.set"}],
        "connections": {
            "Publish files": {
                "main": [[{"node": "Next", "type": "main", "index": 0}]],
                "error": {"main": []},
            }
        },
        "settings": {},
    }
    payload_b = {
        "name": "wf_files_06_chunk_division",
        "nodes": [{"name": "Publish files", "type": "n8n-nodes-base.set"}],
        "connections": {
            "Publish files": {
                "main": [[{"node": "Next", "type": "main", "index": 0}]],
            }
        },
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right, include_settings=False)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_ignores_orphan_connections_without_existing_nodes(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "tool_rag_documents",
        "nodes": [{"name": "Think1", "type": "n8n-nodes-base.set"}],
        "connections": {
            "Think1": {"main": [[{"node": "Think1", "type": "main", "index": 0}]]},
            "Think2": {"ai_tool": [[{"node": "RAG3", "type": "ai_tool", "index": 0}]]},
            "get_document_full_text3": {"ai_tool": [[{"node": "RAG3", "type": "ai_tool", "index": 0}]]},
        },
        "settings": {},
    }
    payload_b = {
        "name": "tool_rag_documents",
        "nodes": [{"name": "Think1", "type": "n8n-nodes-base.set"}],
        "connections": {
            "Think1": {"main": [[{"node": "Think1", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right, include_settings=False)

    assert len(rows) == 1
    assert rows[0].status == "Igual"


def test_compare_can_toggle_endpoint_fields(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "wf_files_04_identify",
        "nodes": [
            {
                "name": "Call API",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "url": "http://service-a:8080/split",
                    "method": "POST",
                },
            }
        ],
        "connections": {},
        "settings": {},
    }
    payload_b = {
        "name": "wf_files_04_identify",
        "nodes": [
            {
                "name": "Call API",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "url": "http://service-b:30080/split",
                    "method": "POST",
                },
            }
        ],
        "connections": {},
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows_default = service.compare_directories(left, right, include_settings=False, include_endpoints=False)
    rows_with_endpoints = service.compare_directories(
        left,
        right,
        include_settings=False,
        include_endpoints=True,
    )

    assert len(rows_default) == 1
    assert rows_default[0].status == "Igual"
    assert len(rows_with_endpoints) == 1
    assert rows_with_endpoints[0].status == "Diferente"


def test_build_workflow_diff_report_includes_changed_fields(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "Fluxo Diff",
        "nodes": [{"name": "N1", "type": "n8n-nodes-base.set", "parameters": {"foo": 1}}],
        "connections": {},
        "settings": {},
    }
    payload_b = {
        "name": "Fluxo Diff",
        "nodes": [{"name": "N1", "type": "n8n-nodes-base.set", "parameters": {"foo": 2}}],
        "connections": {},
        "settings": {},
    }
    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    report = service.build_workflow_diff_report(left, right, "Fluxo Diff", include_settings=False, include_endpoints=False)

    assert "Diferencas encontradas" in report
    assert "nodes[0].parameters.foo" in report


def test_compare_ignores_node_order_when_logic_is_equal(tmp_path: Path) -> None:
    left = tmp_path / "20260521_100000_srv-a"
    right = tmp_path / "20260521_110000_srv-b"
    left.mkdir()
    right.mkdir()

    payload_a = {
        "name": "wf_defense_drafting_05_finalize",
        "nodes": [
            {"name": "Build Full Brief", "type": "n8n-nodes-base.code"},
            {"name": "Call 'generate pdf file'", "type": "n8n-nodes-base.executeWorkflow"},
            {"name": "get only result file", "type": "n8n-nodes-base.set"},
        ],
        "connections": {
            "Build Full Brief": {"main": [[{"node": "Call 'generate pdf file'", "type": "main", "index": 0}]]},
            "Call 'generate pdf file'": {"main": [[{"node": "get only result file", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    payload_b = {
        "name": "wf_defense_drafting_05_finalize",
        "nodes": [
            {"name": "get only result file", "type": "n8n-nodes-base.set"},
            {"name": "Build Full Brief", "type": "n8n-nodes-base.code"},
            {"name": "Call 'generate pdf file'", "type": "n8n-nodes-base.executeWorkflow"},
        ],
        "connections": {
            "Build Full Brief": {"main": [[{"node": "Call 'generate pdf file'", "type": "main", "index": 0}]]},
            "Call 'generate pdf file'": {"main": [[{"node": "get only result file", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }

    (left / "x.json").write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
    (right / "x.json").write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")

    service = BackupCompareService()
    rows = service.compare_directories(left, right)

    assert len(rows) == 1
    assert rows[0].status == "Igual"
