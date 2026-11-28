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
            self.history=[{"name":"done.pdf","status":"Completed","completed_at":1,"time":"2026-11-28 09:00:00","size":4096}]
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
