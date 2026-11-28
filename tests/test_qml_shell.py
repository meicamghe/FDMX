from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "qml_ui"


def _qt():
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    return app


def test_qml_shell_files_exist():
    assert (QML_DIR / "main.py").is_file()
    assert (QML_DIR / "Main.qml").is_file()
    assert (QML_DIR / "README.md").is_file()
    assert (QML_DIR / "models.py").is_file()


def test_qml_shell_is_explicitly_isolated_from_production_engine():
    source = (QML_DIR / "main.py").read_text(encoding="utf-8")
    qml = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert "FDMX_v6_50" not in source
    assert "appBridge" in source
    assert "appBridge.downloadModel" in qml


def test_preview_does_not_claim_live_download_telemetry():
    qml = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    readme = (QML_DIR / "README.md").read_text(encoding="utf-8")
    assert "not connected to the download engine yet" in qml
    assert "not connected" in readme


def test_download_model_normalizes_backend_snapshots():
    _qt()
    from qml_ui.models import DownloadListModel

    model = DownloadListModel()
    model.replace_downloads([{
        "download_id": "task-1",
        "file_name": "sample.zip",
        "status": "Downloading",
        "progress": 135,
        "speed": "2.4 MB/s",
    }])
    assert model.rowCount() == 1
    roles = model.roleNames()
    assert bytes(roles[model.FileNameRole]) == b"fileName"
    assert model.data(model.index(0, 0), model.FileNameRole) == "sample.zip"
    assert model.data(model.index(0, 0), model.ProgressRole) == 100


def test_qml_engine_loads_preview_window():
    _qt()
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine
    from qml_ui.main import AppBridge

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appBridge", AppBridge())
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    assert engine.rootObjects(), "Qt Quick failed to load Main.qml"
    engine.clearComponentCache()
    del engine
