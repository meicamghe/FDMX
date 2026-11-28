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
            self.history=[{"name":"done.pdf","status":"Completed","completed_at":1}]
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
    assert adapter.scheduledDownloads == 0
    assert adapter.settings["maxDownloads"] is None
    assert adapter.totalSpeed == "2.0 KB/s"
    assert adapter.downloads[0]["download_id"] == "active"
    assert adapter.downloadModel.rowCount() == 3
    adapter.pause("active")
    adapter.resume("active")
    assert controller.worker.calls == ["pause","resume"]
    adapter.cancel("queued")
    assert controller.canceled == ["queued"]
    controller.tasks["failed"]={"name":"bad.zip","status":"Failed"}
    adapter.retry("failed")
    assert controller.tasks["failed"]["status"] == "Queued"
    assert controller.scheduled == 1 and controller.saved == 3
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
