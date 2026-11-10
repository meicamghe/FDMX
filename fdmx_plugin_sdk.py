"""FDMX Plugin SDK - first stable API surface.

Plugins execute in the FDMX process. Exceptions are contained per plugin, but this
is NOT a security sandbox: install and enable only plugins from trusted sources.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QTextEdit, QMessageBox
)

SDK_VERSION = "1.0"
ALLOWED_PERMISSIONS = {"app.events", "app.log", "ui.notifications"}
PLUGIN_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str
    description: str
    folder: Path
    entrypoint: str
    permissions: tuple[str, ...]
    enabled: bool = False
    loaded: bool = False
    error: str = ""


class PluginAPI:
    """Capability-limited API exposed to a plugin."""
    def __init__(self, record: PluginRecord, granted: set[str], logger: Callable[[str], None],
                 notifier: Callable[[str, str], None]):
        self.plugin_id = record.plugin_id
        self.plugin_name = record.name
        self._granted = granted
        self._logger = logger
        self._notifier = notifier
        self._hooks: dict[str, list[Callable]] = {}

    def _require(self, permission: str):
        if permission not in self._granted:
            raise PermissionError(f"Plugin '{self.plugin_id}' lacks permission: {permission}")

    def log(self, message: str):
        self._require("app.log")
        self._logger(f"[{self.plugin_id}] {str(message)[:1000]}")

    def notify(self, title: str, message: str):
        self._require("ui.notifications")
        self._notifier(str(title)[:120], str(message)[:1000])

    def on(self, event_name: str, callback: Callable):
        self._require("app.events")
        if not isinstance(event_name, str) or not event_name or len(event_name) > 80:
            raise ValueError("Invalid event name")
        if not callable(callback):
            raise TypeError("Event callback must be callable")
        self._hooks.setdefault(event_name, []).append(callback)

    def _dispatch(self, event_name: str, payload: dict):
        for callback in tuple(self._hooks.get(event_name, ())):
            callback(dict(payload))


class PluginManager:
    def __init__(self, plugin_dir: str | Path, logger: Callable[[str], None] | None = None,
                 notifier: Callable[[str, str], None] | None = None):
        self.plugin_dir = Path(plugin_dir).expanduser()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.plugin_dir.parent / "plugin_state.json"
        self.logger = logger or (lambda message: None)
        self.notifier = notifier or (lambda title, message: None)
        self.records: dict[str, PluginRecord] = {}
        self._modules = {}
        self._apis: dict[str, PluginAPI] = {}
        self._state = self._read_state()

    def _read_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_state(self):
        temp = self.state_file.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.state_file)
        except OSError as exc:
            self.logger(f"Could not save plugin settings: {exc}")

    def scan(self):
        found = {}
        for manifest_path in self.plugin_dir.glob("*/plugin.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugin_id = str(data.get("id", manifest_path.parent.name))
                if not PLUGIN_ID_RE.fullmatch(plugin_id) or plugin_id in found:
                    raise ValueError("Invalid or duplicate plugin id")
                name = str(data.get("name", plugin_id))[:100]
                version = str(data.get("version", "0.0.0"))[:40]
                entrypoint = str(data.get("entrypoint", "plugin.py"))
                if Path(entrypoint).name != entrypoint or not entrypoint.endswith(".py"):
                    raise ValueError("Entrypoint must be a Python file in the plugin folder")
                permissions = tuple(sorted(set(data.get("permissions", []))))
                unknown = set(permissions) - ALLOWED_PERMISSIONS
                if unknown:
                    raise ValueError("Unknown permission(s): " + ", ".join(sorted(unknown)))
                found[plugin_id] = PluginRecord(
                    plugin_id, name, version, str(data.get("description", ""))[:500],
                    manifest_path.parent, entrypoint, permissions,
                    bool(self._state.get(plugin_id, {}).get("enabled", False))
                )
            except Exception as exc:
                self.logger(f"Skipped {manifest_path}: {exc}")
        self.records = found
        return list(found.values())

    def set_enabled(self, plugin_id: str, enabled: bool):
        record = self.records[plugin_id]
        record.enabled = bool(enabled)
        state = self._state.setdefault(plugin_id, {})
        state["enabled"] = record.enabled
        self._save_state()
        if not record.enabled:
            self.unload(plugin_id)

    def load(self, plugin_id: str):
        record = self.records[plugin_id]
        if not record.enabled:
            raise RuntimeError("Enable this plugin before loading it")
        if record.loaded:
            return
        entry = record.folder / record.entrypoint
        if not entry.is_file():
            raise FileNotFoundError(f"Plugin entrypoint not found: {entry.name}")
        module_name = f"fdmx_plugin_{plugin_id.replace('-', '_').replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, entry)
        if spec is None or spec.loader is None:
            raise ImportError("Could not create plugin loader")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        api = PluginAPI(record, set(record.permissions), self.logger, self.notifier)
        try:
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise TypeError("Plugin must define register(api)")
            register(api)
            self._modules[plugin_id] = module
            self._apis[plugin_id] = api
            record.loaded = True
            record.error = ""
            self.logger(f"Loaded {record.name} v{record.version}")
        except Exception as exc:
            sys.modules.pop(module_name, None)
            record.error = f"{type(exc).__name__}: {exc}"
            record.loaded = False
            self.logger(f"Plugin {plugin_id} failed to load: {record.error}")
            self.logger(traceback.format_exc(limit=5))
            raise

    def unload(self, plugin_id: str):
        module = self._modules.pop(plugin_id, None)
        self._apis.pop(plugin_id, None)
        record = self.records.get(plugin_id)
        if module:
            shutdown = getattr(module, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception as exc:
                    self.logger(f"Plugin {plugin_id} shutdown error: {exc}")
            sys.modules.pop(module.__name__, None)
        if record:
            record.loaded = False

    def emit(self, event_name: str, **payload):
        failed = []
        for plugin_id, api in tuple(self._apis.items()):
            try:
                api._dispatch(event_name, payload)
            except Exception as exc:
                failed.append((plugin_id, exc))
        for plugin_id, exc in failed:
            record = self.records.get(plugin_id)
            if record:
                record.error = f"Hook error: {type(exc).__name__}: {exc}"
            self.logger(f"Disabled faulty plugin {plugin_id}: {exc}")
            self.unload(plugin_id)


class PluginManagerDialog(QDialog):
    def __init__(self, manager: PluginManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("FDMX Plugin Manager")
        self.resize(650, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Plugins are trusted Python code and run inside FDMX. Review their source before enabling."))
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        layout.addWidget(self.details)
        buttons = QHBoxLayout()
        self.scan_button = QPushButton("Refresh")
        self.enable_button = QPushButton("Enable")
        self.load_button = QPushButton("Load")
        self.disable_button = QPushButton("Disable")
        self.close_button = QPushButton("Close")
        for button in (self.scan_button, self.enable_button, self.load_button, self.disable_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.scan_button.clicked.connect(self.refresh)
        self.enable_button.clicked.connect(lambda: self._set_enabled(True))
        self.disable_button.clicked.connect(lambda: self._set_enabled(False))
        self.load_button.clicked.connect(self._load_selected)
        self.close_button.clicked.connect(self.accept)
        self.items.currentRowChanged.connect(self._show_details)
        self.refresh()

    def _selected(self):
        item = self.items.currentItem()
        return item.data(256) if item else None

    def refresh(self):
        self.manager.scan()
        self.items.clear()
        for record in sorted(self.manager.records.values(), key=lambda r: r.name.lower()):
            state = "Loaded" if record.loaded else ("Enabled" if record.enabled else "Disabled")
            item = QListWidgetItem(f"{record.name}  v{record.version}  [{state}]")
            item.setData(256, record.plugin_id)
            self.items.addItem(item)
        if self.items.count():
            self.items.setCurrentRow(0)
        else:
            self.details.setPlainText("No plugins found. Place each plugin in its own folder under the FDMX plugins directory with a plugin.json manifest.")

    def _show_details(self, _row):
        plugin_id = self._selected()
        record = self.manager.records.get(plugin_id) if plugin_id else None
        if not record:
            self.details.clear()
            return
        self.details.setPlainText(
            f"{record.description}\nID: {record.plugin_id}\nPermissions: {', '.join(record.permissions) or 'none'}\n"
            f"Status: {'Loaded' if record.loaded else ('Enabled' if record.enabled else 'Disabled')}\n"
            f"Error: {record.error or 'None'}"
        )

    def _set_enabled(self, enabled):
        plugin_id = self._selected()
        if not plugin_id:
            return
        try:
            self.manager.set_enabled(plugin_id, enabled)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Plugin Manager", str(exc))

    def _load_selected(self):
        plugin_id = self._selected()
        if not plugin_id:
            return
        try:
            self.manager.load(plugin_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Plugin load failed", str(exc))
