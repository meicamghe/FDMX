"""FDMX Plugin SDK 1.1 - isolated plugin worker manager.
Plugins run in a separate process. This is crash containment, NOT an OS sandbox.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, threading

from dataclasses import dataclass
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QTextEdit, QMessageBox

SDK_VERSION = "1.2"
ALLOWED_PERMISSIONS = {"app.events", "app.log", "ui.notifications"}
PLUGIN_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
MAX_MESSAGE_BYTES = 1024 * 1024
ALLOWED_EVENTS = {"app.started", "download.completed", "download.failed"}

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

def _build_worker_command(record, host_script, *, frozen=None, executable=None, bundle_dir=None, platform=None):
    """Build a worker launch command for source and PyInstaller deployments."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    platform = platform or sys.platform
    arguments = [str(record.folder), record.entrypoint, record.plugin_id,
                 json.dumps(list(record.permissions))]
    if not frozen:
        return [executable, "-u", str(host_script), *arguments]

    worker_name = "fdmx_plugin_worker.exe" if platform.startswith("win") else "fdmx_plugin_worker"
    candidates = [Path(executable).resolve().parent / worker_name]
    if bundle_dir:
        bundled = Path(bundle_dir) / worker_name
        if bundled not in candidates:
            candidates.append(bundled)
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate), *arguments]
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"Packaged plugin worker '{worker_name}' was not found. "
        f"Place it beside the FDMX executable or bundle it with the application. Searched: {searched}"
    )


class _Worker:
    def __init__(self, record, logger, notifier):
        self.record, self.logger, self.notifier = record, logger, notifier
        self.process = None
        self.ready = threading.Event()
        self.start_error = None
        self.write_lock = threading.Lock()

    def _send(self, message):
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("Plugin IPC message exceeds 1 MiB")
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Plugin worker is not running")
        with self.write_lock:
            self.process.stdin.write(raw + "\n")
            self.process.stdin.flush()

    def start(self):
        host = Path(__file__).with_name("fdmx_plugin_host.py")
        if not host.is_file():
            raise FileNotFoundError("fdmx_plugin_host.py is missing beside fdmx_plugin_sdk.py")
        command = _build_worker_command(self.record, host)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1
        )
        threading.Thread(target=self._read_loop, name=f"FDMXPlugin-{self.record.plugin_id}", daemon=True).start()
        if not self.ready.wait(8.0):
            self.stop()
            raise TimeoutError("Plugin worker startup exceeded 8 seconds")
        if self.start_error:
            self.stop()
            raise RuntimeError(self.start_error)
        if self.process.poll() is not None:
            raise RuntimeError("Plugin worker exited during startup")

    def _read_loop(self):
        try:
            for line in self.process.stdout:
                if len(line.encode("utf-8", errors="replace")) > MAX_MESSAGE_BYTES:
                    self.start_error = "Worker sent an oversized IPC message"
                    break
                try:
                    msg = json.loads(line)
                except Exception:
                    self.start_error = "Worker sent invalid JSON"
                    continue
                kind = msg.get("type")
                if kind == "ready":
                    self.ready.set()
                elif kind == "startup_error":
                    self.start_error = str(msg.get("message", "Plugin startup failed"))[:1000]
                    self.ready.set()
                elif kind == "rpc":
                    self._handle_rpc(msg)
                elif kind == "fatal":
                    self.start_error = str(msg.get("message", "Worker failed"))[:1000]
                    self.ready.set()
                    self.logger(f"Plugin {self.record.plugin_id}: {self.start_error}")
                elif kind == "log":
                    self.logger(f"[{self.record.plugin_id}] {str(msg.get('message', ''))[:1000]}")
        finally:
            self.ready.set()

    def _handle_rpc(self, msg):
        result = {"type": "rpc_result", "id": msg.get("id"), "ok": True}
        try:
            method = msg.get("method")
            if method == "log" and "app.log" in self.record.permissions:
                self.logger(f"[{self.record.plugin_id}] {str(msg.get('message', ''))[:1000]}")
            elif method == "notify" and "ui.notifications" in self.record.permissions:
                self.notifier(str(msg.get("title", ""))[:120], str(msg.get("message", ""))[:1000])
            else:
                raise PermissionError(f"RPC method not permitted: {method}")
        except Exception as exc:
            result.update(ok=False, error=str(exc)[:500])
        try:
            self._send(result)
        except Exception as exc:
            self.logger(f"Plugin IPC response failed: {exc}")

    def emit(self, event_name, payload):
        if "app.events" in self.record.permissions and event_name in ALLOWED_EVENTS:
            self._send({"type": "event", "name": event_name, "payload": payload})

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self._send({"type": "shutdown"})
                self.process.wait(timeout=2.0)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        if self.process:
            for stream in (self.process.stdin, self.process.stdout):
                try: stream.close()
                except Exception: pass

class PluginManager:
    def __init__(self, plugin_dir, logger=None, notifier=None):
        self.plugin_dir = Path(plugin_dir).expanduser()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.plugin_dir.parent / "plugin_state.json"
        self.logger = logger or (lambda message: None)
        self.notifier = notifier or (lambda title, message: None)
        self.records, self._workers = {}, {}
        self._state = self._read_state()

    def _read_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError): return {}

    def _save_state(self):
        temp = self.state_file.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self.state_file)
        except OSError as exc: self.logger(f"Could not save plugin settings: {exc}")

    def scan(self):
        found = {}
        for manifest_path in self.plugin_dir.glob("*/plugin.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                pid = str(data.get("id", manifest_path.parent.name))
                if not PLUGIN_ID_RE.fullmatch(pid) or pid in found: raise ValueError("Invalid or duplicate plugin id")
                entry = str(data.get("entrypoint", "plugin.py"))
                if Path(entry).name != entry or not entry.endswith(".py"): raise ValueError("Entrypoint must be a Python file in plugin folder")
                perms = tuple(sorted(set(data.get("permissions", []))))
                unknown = set(perms) - ALLOWED_PERMISSIONS
                if unknown: raise ValueError("Unknown permission(s): " + ", ".join(sorted(unknown)))
                previous = self.records.get(pid)
                found[pid] = PluginRecord(pid, str(data.get("name", pid))[:100], str(data.get("version", "0.0.0"))[:40],
                    str(data.get("description", ""))[:500], manifest_path.parent, entry, perms,
                    bool(self._state.get(pid, {}).get("enabled", False)),
                    loaded=pid in self._workers,
                    error=previous.error if previous else "")
            except Exception as exc: self.logger(f"Skipped {manifest_path}: {exc}")
        self.records = found
        return list(found.values())

    def set_enabled(self, plugin_id, enabled):
        rec = self.records[plugin_id]
        rec.enabled = bool(enabled)
        self._state.setdefault(plugin_id, {})["enabled"] = rec.enabled
        self._save_state()
        if not rec.enabled: self.unload(plugin_id)

    def load(self, plugin_id):
        rec = self.records[plugin_id]
        if not rec.enabled: raise RuntimeError("Enable this plugin before loading it")
        if rec.loaded: return
        if not (rec.folder / rec.entrypoint).is_file(): raise FileNotFoundError(f"Plugin entrypoint not found: {rec.entrypoint}")
        worker = _Worker(rec, self.logger, self.notifier)
        try:
            worker.start()
            self._workers[plugin_id] = worker
            rec.loaded, rec.error = True, ""
            self.logger(f"Started isolated worker: {rec.name} v{rec.version}")
        except Exception as exc:
            worker.stop()
            rec.error, rec.loaded = f"{type(exc).__name__}: {exc}", False
            raise

    def unload(self, plugin_id):
        worker = self._workers.pop(plugin_id, None)
        if worker: worker.stop()
        if plugin_id in self.records: self.records[plugin_id].loaded = False

    def emit(self, event_name, **payload):
        if event_name not in ALLOWED_EVENTS: return
        for pid, worker in tuple(self._workers.items()):
            try:
                worker.emit(event_name, payload)
                if worker.process and worker.process.poll() is not None: raise RuntimeError("Worker exited unexpectedly")
            except Exception as exc:
                if pid in self.records: self.records[pid].error = f"Worker error: {type(exc).__name__}: {exc}"
                self.logger(f"Stopping faulty plugin worker {pid}: {exc}")
                self.unload(pid)

    def shutdown(self):
        for pid in tuple(self._workers): self.unload(pid)

class PluginManagerDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("FDMX Plugin Manager")
        self.resize(650, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Plugins run in separate processes. This is crash isolation, not an OS sandbox; plugins retain your user-account permissions."))
        self.items = QListWidget(); layout.addWidget(self.items, 1)
        self.details = QTextEdit(); self.details.setReadOnly(True); self.details.setMaximumHeight(110); layout.addWidget(self.details)
        buttons = QHBoxLayout()
        self.scan_button, self.enable_button = QPushButton("Refresh"), QPushButton("Enable")
        self.load_button, self.disable_button, self.close_button = QPushButton("Load"), QPushButton("Disable"), QPushButton("Close")
        for button in (self.scan_button, self.enable_button, self.load_button, self.disable_button): buttons.addWidget(button)
        buttons.addStretch(1); buttons.addWidget(self.close_button); layout.addLayout(buttons)
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
        self.manager.scan(); self.items.clear()
        for rec in sorted(self.manager.records.values(), key=lambda r: r.name.lower()):
            state = "Running" if rec.loaded else ("Enabled" if rec.enabled else "Disabled")
            item = QListWidgetItem(f"{rec.name}  v{rec.version}  [{state}]")
            item.setData(256, rec.plugin_id); self.items.addItem(item)
        if self.items.count(): self.items.setCurrentRow(0)
        else: self.details.setPlainText("No plugins found. Add a plugin folder containing plugin.json and its Python entrypoint.")

    def _show_details(self, _row):
        pid = self._selected(); rec = self.manager.records.get(pid) if pid else None
        if not rec: self.details.clear(); return
        self.details.setPlainText(f"{rec.description}\nID: {rec.plugin_id}\nPermissions: {', '.join(rec.permissions) or 'none'}\nStatus: {'Running' if rec.loaded else ('Enabled' if rec.enabled else 'Disabled')}\nError: {rec.error or 'None'}")

    def _set_enabled(self, enabled):
        pid = self._selected()
        if not pid: return
        try: self.manager.set_enabled(pid, enabled); self.refresh()
        except Exception as exc: QMessageBox.warning(self, "Plugin Manager", str(exc))

    def _load_selected(self):
        pid = self._selected()
        if not pid: return
        try: self.manager.load(pid); self.refresh()
        except Exception as exc: QMessageBox.warning(self, "Plugin load failed", str(exc))
