from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "qml_ui"

def _qt():
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])

def test_qml_shell_files_exist():
    for name in ("main.py", "Main.qml", "README.md", "models.py", "adapter.py", "host.py"):
        assert (QML_DIR / name).is_file()

def test_preview_remains_isolated():
    source = (QML_DIR / "main.py").read_text(encoding="utf-8")
    assert "FDMX_v6_50" not in source
    host = (QML_DIR / "host.py").read_text(encoding="utf-8")
    assert "QApplication.instance()" in host
    assert "QApplication(" not in host

def test_download_model_normalizes_backend_fields():
    _qt()
    from qml_ui.models import DownloadListModel
    model = DownloadListModel()
    model.replace_downloads([{"download_id":"task-1","file_name":"sample.zip","status":"Downloading","progress":135,"speed_text":"2.4 MB/s","downloaded":135,"total":100,"category":"Archive"}])
    assert model.rowCount() == 1
    index = model.index(0, 0)
    assert model.data(index, model.FileNameRole) == "sample.zip"
    assert model.data(index, model.ProgressRole) == 100
    assert model.data(index, model.DownloadedRole) == 135
    assert model.data(index, model.CategoryRole) == "Archive"
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    model.replace_downloads([{"download_id":"task-1","file_name":"sample.zip","status":"Downloading","progress":100,"speed_text":"2.4 MB/s","downloaded":135,"total":100,"category":"Archive"}])
    assert resets == []  # identical polling snapshots preserve view state
    updates = []
    model.dataChanged.connect(lambda first, last, roles: updates.append((first.row(), last.row(), roles)))
    model.replace_downloads([{"download_id":"task-1","file_name":"sample.zip","status":"Downloading","progress":50,"speed_text":"1.2 MB/s","downloaded":50,"total":100,"category":"Archive"}])
    assert resets == []
    assert len(updates) == 1 and updates[0][0:2] == (0, 0)
    assert model.data(model.index(0, 0), model.ProgressRole) == 50
    model.replace_downloads([{"download_id":"task-1","file_name":"sample.zip"}, {"download_id":"task-2","file_name":"other.zip"}])
    assert resets == [True] and model.rowCount() == 2  # identity changes reset once

def test_adapter_snapshots_stats_and_task_id_actions():
    _qt()
    from PySide6.QtCore import QObject
    from qml_ui.adapter import FDMXDownloadAdapter
    class Worker:
        def __init__(self): self.calls=[]
        def pause(self): self.calls.append("pause")
        def resume(self): self.calls.append("resume")
    class Controller(QObject):
        def __init__(self):
            super().__init__()
            self.worker=Worker()
            self.tasks={
                "active":{"name":"active.bin","status":"Downloading","downloaded":50,"total":100,"speed":2048,"worker":self.worker},
                "queued":{"name":"queued.zip","status":"Queued","worker":None},
                "done":{"name":"done.pdf","status":"Completed","downloaded":10,"total":10},
            }
            self.history=[{"name":"done.pdf","status":"Completed","completed_at":1,"time":"2026-11-28 09:00:00","size":4096,"error":"Request failed at https://secret.example/private/file"}]
            self.saved=0; self.scheduled=0; self.canceled=[]
        def save_tasks(self): self.saved+=1
        def schedule_downloads(self): self.scheduled+=1
        def cancel_task(self, task_id): self.canceled.append(task_id)
    controller=Controller()
    adapter=FDMXDownloadAdapter(controller, interval_ms=100000)
    assert adapter.activeDownloads == 1
    assert adapter.queuedDownloads == 1
    assert adapter.completedDownloads == 1
    assert adapter.history[0]["file_name"] == "done.pdf"
    assert adapter.history[0]["size"] == 4096
    assert adapter.history[0]["time"] == "2026-11-28 09:00:00"
    assert "url" not in adapter.history[0] and "path" not in adapter.history[0]
    assert adapter.history[0]["error"] == "See the application log for details."
    assert "secret.example" not in str(adapter.history[0])
    assert adapter.scheduledDownloads == 0
    assert adapter.settings["maxDownloads"] is None
    assert adapter.totalSpeed == "2.0 KB/s"
    assert adapter.downloads[0]["download_id"] == "active"
    assert adapter.downloadModel.rowCount() == 3
    rejected = []
    adapter.actionRejected.connect(rejected.append)
    adapter.pause("missing")
    assert rejected and "cannot be paused" in rejected[-1]
    adapter.pause("active")
    adapter.resume("active")
    assert controller.worker.calls == ["pause","resume"]
    adapter.cancel("queued")
    assert controller.canceled == ["queued"]
    controller.tasks["failed"]={"name":"bad.zip","status":"Failed"}
    adapter.retry("failed")
    assert controller.tasks["failed"]["status"] == "Queued"
    assert controller.scheduled == 1 and controller.saved == 3
    adapter.setSchedule("queued", "2099-01-01T12:00:00")
    assert controller.tasks["queued"]["scheduled_at"] == "2099-01-01T12:00:00"
    adapter.clearSchedule("queued")
    assert controller.tasks["queued"]["scheduled_at"] == ""
    adapter.setSchedule("queued", "not-a-date")
    assert "ISO format" in rejected[-1]
    adapter.setSchedule("queued", "2099-01-01T12:00:00")
    adapter.startNow("queued")
    assert controller.tasks["queued"]["scheduled_at"] == ""
    assert controller.scheduled == 2 and controller.saved == 7
    adapter._timer.stop()

def test_qml_engine_loads_preview_window():
    _qt()
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from qml_ui.main import AppBridge
    engine=QQmlApplicationEngine()
    bridge=AppBridge()
    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    assert engine.rootObjects()
    engine.clearComponentCache()
    del engine


def test_production_host_embeds_into_existing_qapplication():
    import os
    import subprocess
    import sys
    script = r"""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from qml_ui.host import create_qml_window
app = QApplication([])
class Controller(QObject):
    def __init__(self):
        super().__init__()
        self.tasks = {}
        self.history = []
controller = Controller()
engine, adapter, root = create_qml_window(controller)
assert root is not None
assert adapter.downloadModel.rowCount() == 0
root.close()
engine.deleteLater()
adapter._timer.stop()
print("production QApplication host smoke passed")
"""
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production QApplication host smoke passed" in result.stdout


def test_qml_exposes_history_and_scheduler_actions():
    source = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    for marker in (
        'id: historyList',
        'appBridge.setSchedule(',
        'appBridge.clearSchedule(',
        'appBridge.startNow(',
        'function onActionRejected(message)',
    ):
        assert marker in source


def test_adapter_submits_links_through_legacy_intake_without_clobbering_input():
    _qt()
    from PySide6.QtCore import QObject
    from qml_ui.adapter import FDMXDownloadAdapter

    class Field:
        def __init__(self, value=""):
            self.value = value
        def text(self):
            return self.value
        def setText(self, value):
            self.value = value

    class Controller(QObject):
        def __init__(self):
            super().__init__()
            self.url = Field("user is editing")
            self.folder = Field("/tmp/adm-downloads")
            self.tasks = {}
            self.history = []
            self.submitted = []
        def add_download(self):
            value = self.url.text()
            self.submitted.append((value, self._pending_qml_handoff, self._pending_qml_schedule_at))
            task_id = f"task-{len(self.submitted)}"
            self.tasks[task_id] = {
                "name": "sample.bin", "status": "Checking metadata",
                "url": value, "folder": self.folder.text(),
            }

    controller = Controller()
    adapter = FDMXDownloadAdapter(controller, interval_ms=100000)
    rejected = []
    adapter.actionRejected.connect(rejected.append)
    adapter.queueDownload("https://example.test/sample.bin")
    assert controller.submitted == [("https://example.test/sample.bin", True, "")]
    assert controller.url.text() == "user is editing"
    assert adapter.downloadModel.rowCount() == 1
    adapter.queueDownload("file:///etc/passwd")
    assert rejected and "valid HTTP" in rejected[-1]
    assert len(controller.submitted) == 1
    adapter._timer.stop()


def test_qml_exposes_real_download_intake():
    source = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert 'placeholderText: "Paste a download link or magnet URL…"' in source
    assert "appBridge.queueDownload(downloadUrlField.text, scheduleInput.text)" in source
    assert 'placeholderText: "Optional start: YYYY-MM-DDTHH:MM"' in source


def test_legacy_controller_suppresses_widgets_detail_windows_for_qml_handoff():
    source = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")
    assert 'qml_handoff = bool(getattr(self, "_pending_qml_handoff", False))' in source
    assert 'not task.get("qml_handoff")' in source
    assert '"qml_handoff": qml_handoff' in source
    assert '"qml_handoff"' in source[source.index("def save_tasks(self):"):source.index("def load_history(self):")]
    assert 'bool(entry.get("qml_handoff", False))' in source
    adapter = (QML_DIR / "adapter.py").read_text(encoding="utf-8")
    assert 'self._controller._pending_qml_handoff = True' in adapter


def test_adapter_passes_future_schedule_to_legacy_download_intake():
    _qt()
    from PySide6.QtCore import QObject
    from qml_ui.adapter import FDMXDownloadAdapter

    class Field:
        def __init__(self, value=""):
            self.value = value
        def text(self):
            return self.value
        def setText(self, value):
            self.value = value

    class Controller(QObject):
        def __init__(self):
            super().__init__()
            self.url = Field()
            self.folder = Field("/tmp/adm-downloads")
            self.tasks = {}
            self.history = []
            self.received_schedule = ""
        def add_download(self):
            self.received_schedule = self._pending_qml_schedule_at
            self.tasks["scheduled-task"] = {
                "name": "later.zip", "status": "Queued",
                "scheduled_at": self.received_schedule,
            }

    controller = Controller()
    adapter = FDMXDownloadAdapter(controller, interval_ms=100000)
    adapter.queueDownload("https://example.test/later.zip", "2099-01-01T12:00:00")
    assert controller.received_schedule == "2099-01-01T12:00:00"
    assert adapter.scheduledDownloads == 1
    rejected = []
    adapter.actionRejected.connect(rejected.append)
    adapter.queueDownload("https://example.test/invalid.zip", "yesterday")
    assert rejected and "future schedule" in rejected[-1]
    adapter._timer.stop()


def test_start_now_persists_schedule_rollback_when_scheduler_fails():
    _qt()
    from PySide6.QtCore import QObject
    from qml_ui.adapter import FDMXDownloadAdapter

    class Controller(QObject):
        def __init__(self):
            super().__init__()
            self.tasks = {
                "scheduled": {
                    "name": "later.zip", "status": "Queued",
                    "scheduled_at": "2099-01-01T12:00:00",
                }
            }
            self.history = []
            self.persisted = []
        def save_tasks(self):
            self.persisted.append(self.tasks["scheduled"]["scheduled_at"])
        def schedule_downloads(self):
            raise RuntimeError("simulated scheduler failure")

    controller = Controller()
    adapter = FDMXDownloadAdapter(controller, interval_ms=100000)
    rejected = []
    adapter.actionRejected.connect(rejected.append)
    adapter.startNow("scheduled")
    assert controller.tasks["scheduled"]["scheduled_at"] == "2099-01-01T12:00:00"
    assert controller.persisted == ["", "2099-01-01T12:00:00"]
    assert rejected and "previous schedule was restored" in rejected[-1]
    adapter._timer.stop()


def test_standalone_preview_bridge_matches_qml_contract():
    _qt()
    from qml_ui.main import AppBridge
    bridge = AppBridge()
    assert bridge.settings["downloadFolder"] == "Preview only"
    assert bridge.history == []
    assert bridge.downloads == []
    assert bridge.queuedDownloads == 0
    assert bridge.scheduledDownloads == 0
    rejected = []
    bridge.actionRejected.connect(rejected.append)
    bridge.queueDownload("https://example.test/file.zip", "")
    bridge.setSchedule("task", "2099-01-01T12:00:00")
    assert len(rejected) == 2


def test_resume_requeues_interrupted_task_without_live_worker():
    _qt()
    from PySide6.QtCore import QObject
    from qml_ui.adapter import FDMXDownloadAdapter

    class Controller(QObject):
        def __init__(self):
            super().__init__()
            self.tasks = {
                "restored": {"name": "partial.zip", "status": "Paused", "worker": None}
            }
            self.history = []
            self.saved = 0
            self.scheduled = 0
        def save_tasks(self):
            self.saved += 1
        def schedule_downloads(self):
            self.scheduled += 1

    controller = Controller()
    adapter = FDMXDownloadAdapter(controller, interval_ms=100000)
    adapter.resume("restored")
    assert controller.tasks["restored"]["status"] == "Queued"
    assert controller.saved == 1
    assert controller.scheduled == 1
    adapter._timer.stop()


def test_real_http_transfer_through_qml_bridge_and_legacy_engine():
    import os
    import subprocess
    import sys
    script = r"""
import importlib.util
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

data_root = tempfile.mkdtemp(prefix="adm-qml-e2e-")
os.environ["HOME"] = data_root
os.environ["USERPROFILE"] = data_root

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, data_root)

payload = bytes((index * 37) % 256 for index in range(64 * 1024))

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", 'attachment; filename="qml-transfer.bin"')
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        value = self.headers.get("Range", "")
        if value.startswith("bytes="):
            start_text, end_text = value[6:].split("-", 1)
            start = int(start_text or 0)
            end = min(int(end_text) if end_text else len(payload) - 1, len(payload) - 1)
            body = payload[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
        else:
            body = payload
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", 'attachment; filename="qml-transfer.bin"')
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

from PySide6.QtCore import QCoreApplication
app = QApplication([])
import sys
sys.path.insert(0, os.getcwd())

spec = importlib.util.spec_from_file_location("fdmx_e2e", Path("FDMX_v6_50.py"))
fdmx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fdmx)
fdmx.FDMX.finish_deferred_startup = lambda self: None

from qml_ui.host import create_qml_window
controller = fdmx.FDMX()
controller.folder.setText(data_root)
controller.max_downloads.setValue(1)
controller.parts_count.setValue(1)
engine, adapter, root = create_qml_window(controller)

url = f"http://127.0.0.1:{server.server_port}/qml-transfer.bin"
adapter.queueDownload(url)
task_id = next(iter(controller.tasks))
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    app.processEvents()
    task = controller.tasks[task_id]
    if task.get("status") in ("Completed", "Failed", "Canceled"):
        break
    time.sleep(0.01)

task = controller.tasks[task_id]
target = Path(data_root) / "qml-transfer.bin"
assert task.get("status") == "Completed", f"QML transfer ended as {task.get('status')}: {controller.status.text()}"
assert task.get("qml_handoff") is True
assert target.is_file(), f"Downloaded file was not created: {target}"
assert target.read_bytes() == payload, "Downloaded bytes differ from the local HTTP fixture"
assert not controller.detail_windows, "QML-originated transfer unexpectedly opened a legacy detail dialog"
adapter.refresh()
assert adapter.downloadModel.rowCount() == 1
assert adapter.downloads[0]["status"] == "Completed"

root.close()
adapter._timer.stop()
engine.deleteLater()
controller.close()
server.shutdown()
server.server_close()
print("real local HTTP transfer through QML bridge and legacy engine passed")
"""
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "real local HTTP transfer through QML bridge and legacy engine passed" in result.stdout


def test_production_qml_launcher_is_separate_and_preserves_legacy_close_flow():
    source = (QML_DIR / "production_main.py").read_text(encoding="utf-8")
    assert "create_qml_window(controller)" in source
    assert "controller.close()" in source
    assert "controller.show()" in source
    assert "parse_gns_protocol_request" in source
