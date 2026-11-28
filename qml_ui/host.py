"""Embed the QML window into the existing production QApplication.

Call this from the existing FDMX QWidget application's GUI thread. This module
never creates a QApplication/QGuiApplication of its own.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl
from pathlib import Path

from .adapter import FDMXDownloadAdapter


def create_qml_window(controller):
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QML host requires the existing QApplication")
    if controller.thread() != app.thread():
        raise RuntimeError("Controller and QApplication must share the GUI thread")

    adapter = FDMXDownloadAdapter(controller, parent=controller)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appBridge", adapter)
    qml_file = Path(__file__).with_name("Main.qml")
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        adapter._timer.stop()
        adapter.deleteLater()
        engine.deleteLater()
        raise RuntimeError("Failed to load ADM QML window; the Widgets host remains available")
    # Return both objects: the caller must retain the engine for the window's
    # lifetime. The adapter is parented to the controller.
    return engine, adapter, engine.rootObjects()[0]
