from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "qml_ui"


def test_qml_shell_files_exist():
    assert (QML_DIR / "main.py").is_file()
    assert (QML_DIR / "Main.qml").is_file()
    assert (QML_DIR / "README.md").is_file()


def test_qml_shell_is_explicitly_isolated_from_production_engine():
    source = (QML_DIR / "main.py").read_text(encoding="utf-8")
    qml = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    assert "FDMX_v6_50" not in source
    assert "appBridge" in source
    assert "appBridge" in qml


def test_preview_does_not_claim_live_download_telemetry():
    qml = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    readme = (QML_DIR / "README.md").read_text(encoding="utf-8")
    assert "not connected to the download engine yet" in qml
    assert "placeholders" in readme


def test_qml_engine_loads_preview_window():
    import pytest

    pytest.importorskip("PySide6")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from qml_ui.main import AppBridge

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appBridge", AppBridge())
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    assert engine.rootObjects(), "Qt Quick failed to load Main.qml"
    engine.clearComponentCache()
    del engine
    app.quit()
