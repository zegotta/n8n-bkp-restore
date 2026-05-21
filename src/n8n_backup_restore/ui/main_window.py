from __future__ import annotations

import json
import logging
import re
import difflib
import html
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QProgressDialog,
    QStyle,
    QDialog,
    QDialogButtonBox,
    QCheckBox as QtCheckBoxWidget,
    QTextEdit,
)

from n8n_backup_restore.models.entities import AppSettings, ServerConfig, WorkflowRecord
from n8n_backup_restore import __version__
from n8n_backup_restore.services.backup_service import BackupService
from n8n_backup_restore.services.backup_compare_service import BackupCompareService
from n8n_backup_restore.services.restore_service import RestoreOptions, RestoreService
from n8n_backup_restore.services.workflow_mcp_service import WorkflowMcpService
from n8n_backup_restore.storage.settings_store import SettingsStore


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings_store: SettingsStore,
        workflow_service: WorkflowMcpService,
        restore_service: RestoreService,
        logger: logging.Logger,
    ) -> None:
        super().__init__()
        self.settings_store = settings_store
        self.workflow_service = workflow_service
        self.restore_service = restore_service
        self.logger = logger
        self.settings = self.settings_store.load()
        self._workflows_loaded: list[WorkflowRecord] = []
        self._editing_server_alias: str | None = None
        self._restore_backup_options: dict[str, Path] = {}
        self._compare_backup_options: dict[str, Path] = {}
        self._restore_workflows_loaded: list[WorkflowRecord] = []
        self._restore_workflow_files: list[Path] = []
        self._pressed_backup_checkbox_state: bool | None = None
        self._pressed_restore_checkbox_state: bool | None = None
        self._restore_apply_all_decision: bool | None = None
        self._backup_compare_service = BackupCompareService()

        self.setWindowTitle("n8n Backup/Restore")
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.resize(1100, 700)
        self._build_ui()
        self._build_menu()
        self._apply_style()
        self._refresh_all()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        tabs = QTabWidget()
        tabs.addTab(self._build_servers_tab(), "Servidores")
        tabs.addTab(self._build_backup_tab(), "Backup")
        tabs.addTab(self._build_restore_tab(), "Restore")
        tabs.addTab(self._build_compare_backups_tab(), "Comparar Backups")
        layout.addWidget(tabs)
        self.setCentralWidget(root)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        menu_arquivo = menu_bar.addMenu("Arquivo")
        action_sair = QAction("Sair", self)
        action_sair.triggered.connect(self.close)
        menu_arquivo.addAction(action_sair)

        menu_editar = menu_bar.addMenu("Editar")
        action_config = QAction("Configurações", self)
        action_config.triggered.connect(self._open_settings_dialog)
        menu_editar.addAction(action_config)

        menu_sobre = menu_bar.addMenu("Sobre")
        action_about = QAction("About", self)
        action_about.triggered.connect(self._show_about_dialog)
        menu_sobre.addAction(action_about)

    def _build_servers_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.servers_table = QTableWidget(0, 4)
        self.servers_table.setHorizontalHeaderLabels(["Alias", "URL", "Token", "Ações"])
        self.servers_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.servers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.servers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.servers_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.servers_table)

        form_box = QGroupBox("Cadastro")
        form_layout = QFormLayout(form_box)
        self.alias_input = QLineEdit()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://seu-n8n.exemplo.com")
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("API key (X-N8N-API-KEY)")
        form_layout.addRow("Alias (único)", self.alias_input)
        form_layout.addRow("URL da instância n8n", self.url_input)
        form_layout.addRow("API Key", self.token_input)
        layout.addWidget(form_box)

        buttons = QHBoxLayout()
        self.btn_add_server = QPushButton("Salvar servidor")
        self.btn_add_server.clicked.connect(self._save_server)
        self.btn_add_server.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        buttons.addWidget(self.btn_add_server)
        buttons.addStretch()
        layout.addLayout(buttons)

        return page

    def _build_backup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.backup_server_combo = QComboBox()
        self.backup_server_combo.currentIndexChanged.connect(self._on_backup_server_changed)
        self.btn_load_workflows = QPushButton("Carregar workflows")
        self.btn_load_workflows.clicked.connect(self._load_workflows_for_backup)
        self.btn_load_workflows.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        top.addWidget(QLabel("Servidor"))
        top.addWidget(self.backup_server_combo)
        top.addWidget(self.btn_load_workflows)
        top.addStretch()
        layout.addLayout(top)

        self.backup_workflows_table = QTableWidget(0, 5)
        self.backup_workflows_table.setHorizontalHeaderLabels(
            ["", "Nome do fluxo", "ID", "Criado em", "Atualizado em"]
        )
        self.backup_workflows_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.backup_workflows_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.backup_workflows_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.backup_workflows_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.backup_workflows_table.cellPressed.connect(self._on_backup_workflows_table_cell_pressed)
        self.backup_workflows_table.cellClicked.connect(self._on_backup_workflows_table_cell_clicked)
        layout.addWidget(self.backup_workflows_table)

        selection_buttons = QHBoxLayout()
        self.btn_check_all_workflows = QPushButton("Marcar todos")
        self.btn_uncheck_all_workflows = QPushButton("Desmarcar todos")
        self.btn_check_all_workflows.clicked.connect(self._check_all_workflows)
        self.btn_uncheck_all_workflows.clicked.connect(self._uncheck_all_workflows)
        self.btn_check_all_workflows.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.btn_uncheck_all_workflows.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogNoButton))
        selection_buttons.addWidget(self.btn_check_all_workflows)
        selection_buttons.addWidget(self.btn_uncheck_all_workflows)
        selection_buttons.addStretch()
        layout.addLayout(selection_buttons)

        self.backup_progress = QProgressBar()
        self.backup_progress.setMinimum(0)
        self.backup_progress.setMaximum(100)
        self.backup_progress.setValue(0)
        self.backup_progress.setFormat("%p% (%v/%m)")
        self.backup_progress.setVisible(False)
        layout.addWidget(self.backup_progress)

        self.btn_run_backup = QPushButton("Executar backup")
        self.btn_run_backup.clicked.connect(self._run_backup)
        self.btn_run_backup.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        layout.addWidget(self.btn_run_backup)
        return page

    def _build_restore_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        line = QHBoxLayout()
        self.restore_server_combo = QComboBox()
        self.restore_server_combo.currentIndexChanged.connect(self._on_restore_server_changed)
        line.addWidget(QLabel("Servidor de destino"))
        line.addWidget(self.restore_server_combo)
        layout.addLayout(line)

        backup_line = QHBoxLayout()
        self.restore_backup_combo = QComboBox()
        self.btn_reload_restore_backups = QPushButton("Atualizar backups")
        self.btn_reload_restore_backups.clicked.connect(self._refresh_restore_backup_options)
        self.btn_reload_restore_backups.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.restore_backup_combo.currentIndexChanged.connect(self._on_restore_backup_changed)
        backup_line.addWidget(QLabel("Backup de origem"))
        backup_line.addWidget(self.restore_backup_combo)
        backup_line.addWidget(self.btn_reload_restore_backups)
        layout.addLayout(backup_line)

        self.restore_workflows_table = QTableWidget(0, 5)
        self.restore_workflows_table.setHorizontalHeaderLabels(
            ["", "Nome do fluxo", "ID", "Criado em", "Atualizado em"]
        )
        self.restore_workflows_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.restore_workflows_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.restore_workflows_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.restore_workflows_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.restore_workflows_table.cellPressed.connect(self._on_restore_workflows_table_cell_pressed)
        self.restore_workflows_table.cellClicked.connect(self._on_restore_workflows_table_cell_clicked)
        layout.addWidget(self.restore_workflows_table, 1)

        restore_selection_buttons = QHBoxLayout()
        self.btn_check_all_restore_workflows = QPushButton("Marcar todos")
        self.btn_uncheck_all_restore_workflows = QPushButton("Desmarcar todos")
        self.btn_check_all_restore_workflows.clicked.connect(self._check_all_restore_workflows)
        self.btn_uncheck_all_restore_workflows.clicked.connect(self._uncheck_all_restore_workflows)
        self.btn_check_all_restore_workflows.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        self.btn_uncheck_all_restore_workflows.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogNoButton))
        restore_selection_buttons.addWidget(self.btn_check_all_restore_workflows)
        restore_selection_buttons.addWidget(self.btn_uncheck_all_restore_workflows)
        restore_selection_buttons.addStretch()
        layout.addLayout(restore_selection_buttons)

        self.btn_run_restore = QPushButton("Executar restore")
        self.btn_run_restore.clicked.connect(self._run_restore)
        self.btn_run_restore.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        layout.addWidget(self.btn_run_restore)
        return page

    def _build_compare_backups_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        top = QHBoxLayout()
        self.compare_backup_left_combo = QComboBox()
        self.compare_backup_right_combo = QComboBox()
        self.btn_reload_compare_backups = QPushButton("Atualizar backups")
        self.btn_reload_compare_backups.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.btn_reload_compare_backups.clicked.connect(self._refresh_compare_backup_options)
        top.addWidget(QLabel("Backup A"))
        top.addWidget(self.compare_backup_left_combo)
        top.addWidget(QLabel("Backup B"))
        top.addWidget(self.compare_backup_right_combo)
        top.addWidget(self.btn_reload_compare_backups)
        layout.addLayout(top)

        self.compare_results_table = QTableWidget(0, 4)
        self.compare_results_table.setHorizontalHeaderLabels(["BACKUP A", "BACKUP B", "STATUS", "Detalhes"])
        self.compare_results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.compare_results_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.compare_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.compare_results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.compare_results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.compare_results_table)

        actions = QHBoxLayout()
        self.btn_compare_backups = QPushButton("Comparar")
        self.btn_compare_backups.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.btn_compare_backups.clicked.connect(self._run_compare_backups)
        self.compare_include_settings_checkbox = QCheckBox("Considerar settings", self)
        self.compare_include_settings_checkbox.setChecked(False)
        self.compare_include_endpoints_checkbox = QCheckBox("Comparar URLs/Endpoints", self)
        self.compare_include_endpoints_checkbox.setChecked(False)
        self.compare_summary_label = QLabel("")
        actions.addWidget(self.btn_compare_backups)
        actions.addWidget(self.compare_include_settings_checkbox)
        actions.addWidget(self.compare_include_endpoints_checkbox)
        actions.addWidget(self.compare_summary_label)
        actions.addStretch()
        layout.addLayout(actions)
        return page

    def _apply_style(self) -> None:
        app = QApplication.instance()
        if app:
            app.setStyle("Fusion")
        self.setStyleSheet(
            """
            QWidget { font-size: 13px; }
            QGroupBox { font-weight: 600; border: 1px solid #d9d9d9; border-radius: 6px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { padding: 8px 12px; border-radius: 6px; background: #1f6feb; color: white; border: none; }
            QPushButton:hover { background: #1a5fd1; }
            QLineEdit, QComboBox, QListWidget, QTableWidget { border: 1px solid #c9c9c9; border-radius: 6px; padding: 6px; }
            """
        )

    def _refresh_all(self) -> None:
        self._refresh_servers_table()
        self._refresh_server_combos()
        self._refresh_restore_backup_options()
        self._refresh_compare_backup_options()

    def _refresh_servers_table(self) -> None:
        ordered_servers = sorted(self.settings.servers, key=lambda s: s.alias.lower())
        self.servers_table.setRowCount(len(ordered_servers))
        for row, server in enumerate(ordered_servers):
            self.servers_table.setItem(row, 0, QTableWidgetItem(server.alias))
            self.servers_table.setItem(row, 1, QTableWidgetItem(server.instance_url))
            token_tail = server.api_key[-10:] if len(server.api_key) > 10 else server.api_key
            self.servers_table.setItem(row, 2, QTableWidgetItem(f"*****{token_tail}"))

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(6)

            btn_test = QPushButton("Testar")
            btn_edit = QPushButton("Editar")
            btn_delete = QPushButton("Excluir")
            btn_test.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
            btn_edit.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
            btn_delete.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))

            alias = server.alias
            btn_test.clicked.connect(lambda _, a=alias: self._test_server_connection_alias(a))
            btn_edit.clicked.connect(lambda _, a=alias: self._edit_server_alias(a))
            btn_delete.clicked.connect(lambda _, a=alias: self._remove_server_alias(a))

            action_layout.addWidget(btn_test)
            action_layout.addWidget(btn_edit)
            action_layout.addWidget(btn_delete)
            self.servers_table.setCellWidget(row, 3, actions)

    def _refresh_server_combos(self) -> None:
        aliases = sorted([s.alias for s in self.settings.servers], key=str.lower)
        current_backup_alias = self.backup_server_combo.currentText()
        current_restore_alias = self.restore_server_combo.currentText()

        self.backup_server_combo.blockSignals(True)
        self.backup_server_combo.clear()
        self.backup_server_combo.addItems(aliases)
        if current_backup_alias:
            idx = self.backup_server_combo.findText(current_backup_alias)
            if idx >= 0:
                self.backup_server_combo.setCurrentIndex(idx)
        self.backup_server_combo.blockSignals(False)

        self.restore_server_combo.blockSignals(True)
        self.restore_server_combo.clear()
        self.restore_server_combo.addItems(aliases)
        if current_restore_alias:
            idx = self.restore_server_combo.findText(current_restore_alias)
            if idx >= 0:
                self.restore_server_combo.setCurrentIndex(idx)
        self.restore_server_combo.blockSignals(False)

    def _save_server(self) -> None:
        alias = self.alias_input.text().strip()
        instance_url = self.url_input.text().strip().rstrip("/")
        api_key = self.token_input.text().strip()

        if not alias or not instance_url or not api_key:
            QMessageBox.warning(self, "Validação", "Todos os campos são obrigatórios.")
            return

        selected_idx = None
        if self._editing_server_alias:
            for idx, existing in enumerate(self.settings.servers):
                if existing.alias == self._editing_server_alias:
                    selected_idx = idx
                    break
        for idx, server in enumerate(self.settings.servers):
            if server.alias == alias and idx != selected_idx:
                QMessageBox.warning(self, "Validação", "Alias já existe. Use outro nome.")
                return

        new_server = ServerConfig(alias=alias, instance_url=instance_url, api_key=api_key)
        if selected_idx is None:
            self.settings.servers.append(new_server)
            self.logger.info("Servidor adicionado: %s", alias)
        else:
            self.settings.servers[selected_idx] = new_server
            self.logger.info("Servidor atualizado: %s", alias)
        self._editing_server_alias = None

        self.settings_store.save(self.settings)
        self._refresh_all()
        self._clear_server_form()

    def _get_server_by_alias(self, alias: str) -> ServerConfig | None:
        for server in self.settings.servers:
            if server.alias == alias:
                return server
        return None

    def _clear_server_form(self) -> None:
        self.alias_input.clear()
        self.url_input.clear()
        self.token_input.clear()
        self.alias_input.setFocus()

    def _edit_server_alias(self, alias: str) -> None:
        server = self._get_server_by_alias(alias)
        if server is None:
            return
        self._editing_server_alias = alias
        self.alias_input.setText(server.alias)
        self.url_input.setText(server.instance_url)
        self.token_input.setText(server.api_key)

    def _remove_server_alias(self, alias: str) -> None:
        idx = next((i for i, item in enumerate(self.settings.servers) if item.alias == alias), None)
        if idx is None:
            return
        del self.settings.servers[idx]
        if self._editing_server_alias == alias:
            self._editing_server_alias = None
        self.settings_store.save(self.settings)
        self._refresh_all()
        self.logger.info("Servidor removido: %s", alias)

    def _test_server_connection_alias(self, alias: str) -> None:
        server = self._get_server_by_alias(alias)
        if server is None:
            return
        ok, message = self._run_with_loading(
            "Testando conexão...",
            lambda: self.workflow_service.test_connection(server),
        )
        if ok:
            QMessageBox.information(self, "Teste de conexão", message)
        else:
            QMessageBox.critical(self, "Teste de conexão", message)

    def _load_workflows_for_backup(self) -> None:
        alias = self.backup_server_combo.currentText()
        server = self._get_server_by_alias(alias)
        if server is None:
            QMessageBox.warning(self, "Backup", "Nenhum servidor selecionado.")
            return
        progress_dialog: QProgressDialog | None = None
        try:
            workflows = self._run_with_loading(
                "Carregando workflows...",
                lambda: self.workflow_service.list_mcp_enabled_workflows(server),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Backup", f"Erro ao carregar workflows: {exc}")
            return

        self._workflows_loaded = sorted(workflows, key=lambda w: w.name.lower())
        self.backup_workflows_table.setRowCount(len(self._workflows_loaded))
        for row, item in enumerate(self._workflows_loaded):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if not self._is_workflow_mcp_enabled(item):
                check_item.setFlags(check_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.backup_workflows_table.setItem(row, 0, check_item)
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox = QtCheckBoxWidget(checkbox_container)
            checkbox.setChecked(False)
            if not self._is_workflow_mcp_enabled(item):
                checkbox.setEnabled(False)
                checkbox.setToolTip("Workflow sem MCP habilitado; não pode ser incluído no backup.")
            checkbox_layout.addWidget(checkbox)
            self.backup_workflows_table.setCellWidget(row, 0, checkbox_container)

            self.backup_workflows_table.setItem(row, 1, QTableWidgetItem(item.name))
            self.backup_workflows_table.setItem(row, 2, QTableWidgetItem(item.workflow_id))
            self.backup_workflows_table.setItem(row, 3, QTableWidgetItem(self._workflow_date(item, "createdAt")))
            self.backup_workflows_table.setItem(row, 4, QTableWidgetItem(self._workflow_date(item, "updatedAt")))
        self.logger.info("Workflows carregados para backup: %s", len(workflows))

    def _on_backup_server_changed(self, _index: int) -> None:
        self._workflows_loaded = []
        self._pressed_backup_checkbox_state = None
        self.backup_workflows_table.setRowCount(0)

    def _run_backup(self) -> None:
        alias = self.backup_server_combo.currentText()
        server = self._get_server_by_alias(alias)
        if server is None:
            QMessageBox.warning(self, "Backup", "Nenhum servidor selecionado.")
            return
        selected: list[WorkflowRecord] = []
        for idx in range(self.backup_workflows_table.rowCount()):
            list_item = self.backup_workflows_table.item(idx, 0)
            checkbox = self._backup_checkbox_at(idx)
            workflow = self._workflows_loaded[idx]
            if (
                list_item is not None
                and checkbox is not None
                and checkbox.isChecked()
                and self._is_workflow_mcp_enabled(workflow)
            ):
                selected.append(workflow)
        if not selected:
            QMessageBox.warning(self, "Backup", "Selecione ao menos um workflow.")
            return

        try:
            selected_full: list[WorkflowRecord] = []
            failed_details = 0
            progress_dialog = QProgressDialog("Executando backup...", "", 0, len(selected), self)
            progress_dialog.setWindowTitle("Aguarde")
            progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            progress_dialog.setCancelButton(None)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)
            progress_dialog.show()
            QApplication.processEvents()

            for idx, workflow in enumerate(selected, start=1):
                try:
                    selected_full.append(self.workflow_service.load_full_workflow(server, None, workflow))
                except Exception as exc:  # noqa: BLE001
                    failed_details += 1
                    self.logger.warning(
                        "Falha ao carregar detalhes do workflow %s (%s): %s",
                        workflow.name,
                        workflow.workflow_id,
                        exc,
                    )
                    selected_full.append(workflow)
                progress_dialog.setValue(idx)
                QApplication.processEvents()

            backup_service = BackupService(self.settings.backups_dir)
            target_dir = backup_service.create_backup_dir(server)
            amount = backup_service.save_workflows(target_dir, selected_full)
            self.logger.info("Backup concluído. Servidor=%s, itens=%s, pasta=%s", alias, amount, target_dir)
            QMessageBox.information(
                self,
                "Backup",
                "Backup concluído com sucesso."
                + (f"\nFluxos com fallback sem detalhes: {failed_details}" if failed_details else "")
                + f"\nPasta: {target_dir}\nArquivos: {amount}",
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Falha no backup: %s", exc)
            QMessageBox.critical(self, "Backup", f"Erro no backup: {exc}")
        finally:
            if progress_dialog is not None:
                progress_dialog.close()

    def _check_all_workflows(self) -> None:
        for idx in range(self.backup_workflows_table.rowCount()):
            checkbox = self._backup_checkbox_at(idx)
            if checkbox is not None and checkbox.isEnabled():
                checkbox.setChecked(True)

    def _uncheck_all_workflows(self) -> None:
        for idx in range(self.backup_workflows_table.rowCount()):
            checkbox = self._backup_checkbox_at(idx)
            if checkbox is not None:
                checkbox.setChecked(False)

    @staticmethod
    def _is_workflow_mcp_enabled(workflow: WorkflowRecord) -> bool:
        raw = workflow.raw if isinstance(workflow.raw, dict) else {}
        for key in ("availableInMCP", "mcpEnabled", "mcp_enabled", "isMcpEnabled", "mcp"):
            value = raw.get(key)
            if isinstance(value, bool):
                return value
        return True

    @staticmethod
    def _workflow_date(workflow: WorkflowRecord, key: str) -> str:
        raw = workflow.raw if isinstance(workflow.raw, dict) else {}
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            return ""
        value = value.strip()
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone()
            return parsed.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            return value

    def _on_backup_workflows_table_cell_clicked(self, row: int, column: int) -> None:
        if column != 0:
            return
        checkbox = self._backup_checkbox_at(row)
        if checkbox is None or not checkbox.isEnabled():
            return
        if (
            self._pressed_backup_checkbox_state is not None
            and checkbox.isChecked() != self._pressed_backup_checkbox_state
        ):
            # Clique direto no checkbox: já houve toggle nativo.
            self._pressed_backup_checkbox_state = None
            return
        checkbox.setChecked(not checkbox.isChecked())
        self._pressed_backup_checkbox_state = None

    def _on_backup_workflows_table_cell_pressed(self, row: int, column: int) -> None:
        if column != 0:
            self._pressed_backup_checkbox_state = None
            return
        checkbox = self._backup_checkbox_at(row)
        self._pressed_backup_checkbox_state = checkbox.isChecked() if checkbox is not None else None

    def _backup_checkbox_at(self, row: int) -> QtCheckBoxWidget | None:
        container = self.backup_workflows_table.cellWidget(row, 0)
        if container is None:
            return None
        checkbox = container.findChild(QtCheckBoxWidget)
        return checkbox

    def _run_with_loading(self, label_text: str, operation):
        dialog = QProgressDialog(label_text, "", 0, 0, self)
        dialog.setWindowTitle("Aguarde")
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setCancelButton(None)
        dialog.setMinimumDuration(0)
        dialog.show()
        QApplication.processEvents()
        try:
            return operation()
        finally:
            dialog.close()

    def _refresh_restore_backup_options(self) -> None:
        self._restore_backup_options.clear()
        self.restore_backup_combo.blockSignals(True)
        self.restore_backup_combo.clear()

        for label, item in self._list_backup_dirs():
            self._restore_backup_options[label] = item
            self.restore_backup_combo.addItem(label)

        self.restore_backup_combo.blockSignals(False)
        self._on_restore_backup_changed()

    def _refresh_compare_backup_options(self) -> None:
        left_selected = self.compare_backup_left_combo.currentText().strip()
        right_selected = self.compare_backup_right_combo.currentText().strip()
        self._compare_backup_options.clear()
        self.compare_backup_left_combo.blockSignals(True)
        self.compare_backup_right_combo.blockSignals(True)
        self.compare_backup_left_combo.clear()
        self.compare_backup_right_combo.clear()

        for label, item in self._list_backup_dirs():
            self._compare_backup_options[label] = item
            self.compare_backup_left_combo.addItem(label)
            self.compare_backup_right_combo.addItem(label)

        if left_selected:
            idx = self.compare_backup_left_combo.findText(left_selected)
            if idx >= 0:
                self.compare_backup_left_combo.setCurrentIndex(idx)
        if right_selected:
            idx = self.compare_backup_right_combo.findText(right_selected)
            if idx >= 0:
                self.compare_backup_right_combo.setCurrentIndex(idx)
        elif self.compare_backup_right_combo.count() > 1:
            self.compare_backup_right_combo.setCurrentIndex(1)

        self.compare_backup_left_combo.blockSignals(False)
        self.compare_backup_right_combo.blockSignals(False)
        self.compare_results_table.setRowCount(0)
        self.compare_summary_label.setText("")

    def _list_backup_dirs(self) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        backups_root = Path(self.settings.backups_dir)
        pattern = re.compile(r"^(\d{8})_(\d{6})_(.+)$")
        if backups_root.exists():
            for item in sorted(backups_root.iterdir(), key=lambda p: p.name, reverse=True):
                if not item.is_dir():
                    continue
                match = pattern.match(item.name)
                if not match:
                    continue
                stamp_date, stamp_time, alias = match.groups()
                try:
                    dt = datetime.strptime(f"{stamp_date}{stamp_time}", "%Y%m%d%H%M%S")
                except ValueError:
                    continue
                label = f"{alias} - {dt.strftime('%d/%m/%Y %H:%M:%S')}"
                out.append((label, item))
        return out

    def _run_compare_backups(self) -> None:
        left_label = self.compare_backup_left_combo.currentText().strip()
        right_label = self.compare_backup_right_combo.currentText().strip()
        left_dir = self._compare_backup_options.get(left_label)
        right_dir = self._compare_backup_options.get(right_label)

        if left_dir is None or right_dir is None:
            QMessageBox.warning(self, "Comparacao", "Selecione dois backups validos.")
            return
        if left_dir == right_dir:
            QMessageBox.warning(self, "Comparacao", "Selecione backups diferentes para comparar.")
            return

        try:
            rows = self._backup_compare_service.compare_directories(
                left_dir,
                right_dir,
                include_settings=self.compare_include_settings_checkbox.isChecked(),
                include_endpoints=self.compare_include_endpoints_checkbox.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Comparacao", f"Erro ao comparar backups: {exc}")
            return

        self.compare_results_table.setRowCount(len(rows))
        equal_count = 0
        diff_count = 0
        only_left_count = 0
        only_right_count = 0
        newer_left_count = 0
        newer_right_count = 0
        for row_idx, row in enumerate(rows):
            item_left = QTableWidgetItem(row.left_name)
            item_right = QTableWidgetItem(row.right_name)
            item_status = QTableWidgetItem(row.status)
            self.compare_results_table.setItem(row_idx, 0, item_left)
            self.compare_results_table.setItem(row_idx, 1, item_right)
            self.compare_results_table.setItem(row_idx, 2, item_status)
            self.compare_results_table.setCellWidget(row_idx, 3, None)
            if row.left_name and row.right_name and row.status != "Igual":
                btn_details = QPushButton("Ver diff")
                btn_details.clicked.connect(
                    lambda _, workflow_name=(row.left_name or row.right_name): self._show_compare_diff_dialog(
                        workflow_name
                    )
                )
                self.compare_results_table.setCellWidget(row_idx, 3, btn_details)
            self._apply_compare_row_color(row_idx, row.status)
            if row.status == "Igual":
                equal_count += 1
            elif row.status == "Diferente":
                diff_count += 1
            elif row.status == "Somente A":
                only_left_count += 1
            elif row.status == "Somente B":
                only_right_count += 1
            elif row.status == "Mais atual em A":
                newer_left_count += 1
            elif row.status == "Mais atual em B":
                newer_right_count += 1

        self.compare_summary_label.setText(
            " | ".join(
                [
                    f"Iguais: {equal_count}",
                    f"Diferentes: {diff_count}",
                    f"Mais atual em A: {newer_left_count}",
                    f"Mais atual em B: {newer_right_count}",
                    f"Somente A: {only_left_count}",
                    f"Somente B: {only_right_count}",
                ]
            )
        )

    def _apply_compare_row_color(self, row_idx: int, status: str) -> None:
        color: QColor | None = None
        if status == "Somente A":
            color = QColor("#E7F0FF")
        elif status == "Somente B":
            color = QColor("#E9F9EE")
        elif status in {"Diferente", "Mais atual em A", "Mais atual em B"}:
            color = QColor("#FFF5E6")

        for column in range(self.compare_results_table.columnCount()):
            item = self.compare_results_table.item(row_idx, column)
            if item is None:
                continue
            if color is not None:
                item.setBackground(color)

    def _show_compare_diff_dialog(self, workflow_name: str) -> None:
        left_label = self.compare_backup_left_combo.currentText().strip()
        right_label = self.compare_backup_right_combo.currentText().strip()
        left_dir = self._compare_backup_options.get(left_label)
        right_dir = self._compare_backup_options.get(right_label)
        if left_dir is None or right_dir is None:
            QMessageBox.warning(self, "Comparacao", "Selecione dois backups validos.")
            return

        diff_entries = self._backup_compare_service.build_workflow_diff_entries(
            left_dir,
            right_dir,
            workflow_name,
            include_settings=self.compare_include_settings_checkbox.isChecked(),
            include_endpoints=self.compare_include_endpoints_checkbox.isChecked(),
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Diferencas - {workflow_name}")
        dialog.setModal(True)
        dialog.resize(980, 640)
        layout = QVBoxLayout(dialog)
        details = QTextEdit(dialog)
        details.setReadOnly(True)
        details.setHtml(self._build_diff_html(workflow_name, left_dir.name, right_dir.name, diff_entries))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.exec()

    def _build_diff_html(
        self,
        workflow_name: str,
        left_backup_name: str,
        right_backup_name: str,
        diff_entries: list[tuple[str, object, object]],
    ) -> str:
        if not diff_entries:
            return (
                f"<h3>{html.escape(workflow_name)}</h3>"
                f"<p><b>Backup A:</b> {html.escape(left_backup_name)}<br>"
                f"<b>Backup B:</b> {html.escape(right_backup_name)}</p>"
                "<p>Sem diferencas no criterio de comparacao atual.</p>"
            )

        parts = [
            f"<h3>{html.escape(workflow_name)}</h3>",
            (
                f"<p><b>Backup A:</b> {html.escape(left_backup_name)}<br>"
                f"<b>Backup B:</b> {html.escape(right_backup_name)}</p>"
            ),
            f"<p><b>Diferencas encontradas:</b> {len(diff_entries)}</p>",
        ]
        for path, left_value, right_value in diff_entries:
            parts.append(f"<hr><p><b>{html.escape(path)}</b></p>")
            if isinstance(left_value, str) and isinstance(right_value, str):
                left_html, right_html = self._highlight_string_diff_html(left_value, right_value)
                parts.append("<p><b>A:</b></p>")
                parts.append(
                    "<pre style='white-space: pre-wrap; word-break: break-word; "
                    "background:#f8f8f8; padding:8px; border:1px solid #ddd;'>"
                    f"{left_html}</pre>"
                )
                parts.append("<p><b>B:</b></p>")
                parts.append(
                    "<pre style='white-space: pre-wrap; word-break: break-word; "
                    "background:#f8f8f8; padding:8px; border:1px solid #ddd;'>"
                    f"{right_html}</pre>"
                )
            else:
                parts.append("<p><b>A:</b></p>")
                parts.append(self._value_block_html(left_value))
                parts.append("<p><b>B:</b></p>")
                parts.append(self._value_block_html(right_value))
        return "".join(parts)

    @staticmethod
    def _value_block_html(value: object) -> str:
        if isinstance(value, str):
            text = value
        elif value == "<missing>":
            text = "<missing>"
        else:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        return (
            "<pre style='white-space: pre-wrap; word-break: break-word; "
            "background:#f8f8f8; padding:8px; border:1px solid #ddd;'>"
            f"{html.escape(text)}</pre>"
        )

    @staticmethod
    def _highlight_string_diff_html(left_value: str, right_value: str) -> tuple[str, str]:
        matcher = difflib.SequenceMatcher(None, left_value, right_value)
        left_parts: list[str] = []
        right_parts: list[str] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            left_chunk = html.escape(left_value[i1:i2])
            right_chunk = html.escape(right_value[j1:j2])
            if tag == "equal":
                left_parts.append(left_chunk)
                right_parts.append(right_chunk)
            elif tag == "replace":
                left_parts.append(f"<span style='background:#ffd6d6;'>{left_chunk}</span>")
                right_parts.append(f"<span style='background:#d9fdd3;'>{right_chunk}</span>")
            elif tag == "delete":
                left_parts.append(f"<span style='background:#ffd6d6;'>{left_chunk}</span>")
            elif tag == "insert":
                right_parts.append(f"<span style='background:#d9fdd3;'>{right_chunk}</span>")
        return "".join(left_parts), "".join(right_parts)

    def _on_restore_backup_changed(self) -> None:
        self.restore_workflows_table.setRowCount(0)
        self._pressed_restore_checkbox_state = None
        self._restore_workflows_loaded = []
        self._restore_workflow_files = []

        label = self.restore_backup_combo.currentText().strip()
        backup_dir = self._restore_backup_options.get(label)
        if backup_dir is None:
            return

        files = sorted(backup_dir.glob("*.json"))
        self._restore_workflow_files = files
        loaded: list[WorkflowRecord] = []
        for file_path in files:
            try:
                raw = json.loads(file_path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raw = {}
            except Exception:  # noqa: BLE001
                raw = {}
            workflow_id = str(raw.get("id") or raw.get("workflowId") or raw.get("workflow_id") or file_path.stem)
            name = str(raw.get("name") or raw.get("workflowName") or file_path.stem)
            loaded.append(WorkflowRecord(workflow_id=workflow_id, name=name, raw=raw))

        self._restore_workflows_loaded = loaded
        self.restore_workflows_table.setRowCount(len(self._restore_workflows_loaded))
        for row, item in enumerate(self._restore_workflows_loaded):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.restore_workflows_table.setItem(row, 0, check_item)
            checkbox_container = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox = QtCheckBoxWidget(checkbox_container)
            checkbox.setChecked(False)
            checkbox_layout.addWidget(checkbox)
            self.restore_workflows_table.setCellWidget(row, 0, checkbox_container)

            self.restore_workflows_table.setItem(row, 1, QTableWidgetItem(item.name))
            self.restore_workflows_table.setItem(row, 2, QTableWidgetItem(item.workflow_id))
            self.restore_workflows_table.setItem(row, 3, QTableWidgetItem(self._workflow_date(item, "createdAt")))
            self.restore_workflows_table.setItem(row, 4, QTableWidgetItem(self._workflow_date(item, "updatedAt")))

    def _on_restore_server_changed(self, _index: int) -> None:
        self._pressed_restore_checkbox_state = None
        self._restore_workflows_loaded = []
        self._restore_workflow_files = []
        self.restore_workflows_table.setRowCount(0)

    def _check_all_restore_workflows(self) -> None:
        for idx in range(self.restore_workflows_table.rowCount()):
            checkbox = self._restore_checkbox_at(idx)
            if checkbox is not None and checkbox.isEnabled():
                checkbox.setChecked(True)

    def _uncheck_all_restore_workflows(self) -> None:
        for idx in range(self.restore_workflows_table.rowCount()):
            checkbox = self._restore_checkbox_at(idx)
            if checkbox is not None:
                checkbox.setChecked(False)

    def _run_restore(self) -> None:
        alias = self.restore_server_combo.currentText()
        server = self._get_server_by_alias(alias)
        backup_label = self.restore_backup_combo.currentText().strip()
        backup_dir = self._restore_backup_options.get(backup_label)

        if server is None:
            QMessageBox.warning(self, "Restore", "Selecione um servidor de destino.")
            return
        if backup_dir is None or not backup_dir.exists():
            QMessageBox.warning(self, "Restore", "Selecione um diretório de backup válido.")
            return
        selected_files: list[Path] = []
        for idx in range(self.restore_workflows_table.rowCount()):
            list_item = self.restore_workflows_table.item(idx, 0)
            checkbox = self._restore_checkbox_at(idx)
            if list_item is not None and checkbox is not None and checkbox.isChecked():
                selected_files.append(self._restore_workflow_files[idx])
        if not selected_files:
            QMessageBox.warning(self, "Restore", "Selecione ao menos um workflow para restaurar.")
            return

        options = RestoreOptions(
            case_sensitive_name_match=self.settings.compare_names_case_sensitive,
            publish_created_workflows=self.settings.publish_created_workflows,
        )
        self._restore_apply_all_decision = None
        progress_dialog = QProgressDialog("Executando restore...", "", 0, len(selected_files), self)
        progress_dialog.setWindowTitle("Aguarde")
        progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()
        QApplication.processEvents()

        def on_progress(current: int, total: int, workflow_name: str) -> None:
            progress_dialog.setMaximum(total)
            progress_dialog.setLabelText(f"Restaurando workflow {current}/{total}: {workflow_name}")
            progress_dialog.setValue(current)
            QApplication.processEvents()

        try:
            restored, skipped = self.restore_service.restore_from_directory(
                server,
                backup_dir,
                selected_files,
                options,
                self._ask_conflict_decision,
                on_progress,
            )
            self.logger.info(
                "Restore concluído. Servidor=%s, restaurados=%s, pulados=%s, origem=%s",
                alias,
                restored,
                skipped,
                backup_dir,
            )
            QMessageBox.information(
                self,
                "Restore",
                f"Restore concluído.\nRestaurados: {restored}\nPulados: {skipped}",
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Falha no restore: %s", exc)
            QMessageBox.critical(self, "Restore", f"Erro no restore: {exc}")
        finally:
            progress_dialog.close()

    def _ask_conflict_decision(self, workflow_name: str, workflow_id: str) -> bool:
        if self._restore_apply_all_decision is not None:
            return self._restore_apply_all_decision

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Conflito de workflow")
        dialog.setText(f"Workflow '{workflow_name}' já existe (id {workflow_id}).\nDeseja substituir?")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        apply_all_check = QCheckBox("Aplicar a todos os fluxos deste restore", dialog)
        dialog.setCheckBox(apply_all_check)
        decision = dialog.exec() == QMessageBox.StandardButton.Yes
        if apply_all_check.isChecked():
            self._restore_apply_all_decision = decision
        return decision

    def _on_restore_workflows_table_cell_clicked(self, row: int, column: int) -> None:
        if column != 0:
            return
        checkbox = self._restore_checkbox_at(row)
        if checkbox is None or not checkbox.isEnabled():
            return
        if (
            self._pressed_restore_checkbox_state is not None
            and checkbox.isChecked() != self._pressed_restore_checkbox_state
        ):
            # Clique direto no checkbox: já houve toggle nativo.
            self._pressed_restore_checkbox_state = None
            return
        checkbox.setChecked(not checkbox.isChecked())
        self._pressed_restore_checkbox_state = None

    def _on_restore_workflows_table_cell_pressed(self, row: int, column: int) -> None:
        if column != 0:
            self._pressed_restore_checkbox_state = None
            return
        checkbox = self._restore_checkbox_at(row)
        self._pressed_restore_checkbox_state = checkbox.isChecked() if checkbox is not None else None

    def _restore_checkbox_at(self, row: int) -> QtCheckBoxWidget | None:
        container = self.restore_workflows_table.cellWidget(row, 0)
        if container is None:
            return None
        checkbox = container.findChild(QtCheckBoxWidget)
        return checkbox

    def _save_settings(self) -> None:
        self.settings.compare_names_case_sensitive = self.settings_case_sensitive_check.isChecked()
        self.settings.publish_created_workflows = self.settings_publish_created_workflows_check.isChecked()
        self.settings.backups_dir = self.settings_backups_dir_input.text().strip() or "./backups"
        self.settings.logs_dir = self.settings_logs_dir_input.text().strip() or "./logs"
        self.settings_store.save(self.settings)
        self._refresh_all()
        QMessageBox.information(self, "Configurações", "Configurações salvas.")
        self.logger.info("Configurações atualizadas.")

    def _open_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Configurações")
        dialog.setModal(True)
        dialog.setMinimumWidth(520)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        self.settings_case_sensitive_check = QCheckBox("Comparar nomes com case-sensitive", dialog)
        self.settings_case_sensitive_check.setChecked(self.settings.compare_names_case_sensitive)
        self.settings_publish_created_workflows_check = QCheckBox(
            "Publicar automaticamente workflows criados no restore",
            dialog,
        )
        self.settings_publish_created_workflows_check.setChecked(self.settings.publish_created_workflows)
        self.settings_backups_dir_input = QLineEdit(dialog)
        self.settings_backups_dir_input.setText(self.settings.backups_dir)
        self.settings_logs_dir_input = QLineEdit(dialog)
        self.settings_logs_dir_input.setText(self.settings.logs_dir)

        form.addRow(self.settings_case_sensitive_check)
        form.addRow(self.settings_publish_created_workflows_check)
        form.addRow("Diretório de backups", self.settings_backups_dir_input)
        form.addRow("Diretório de logs", self.settings_logs_dir_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(lambda: (self._save_settings(), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            "About",
            "n8n Backup/Restore\n"
            f"Versão: {__version__}\n\n"
            "Aplicativo desktop para backup e restore de workflows n8n via API.",
        )
