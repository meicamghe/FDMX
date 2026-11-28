"""Standalone Qt Quick preview; production injects FDMXDownloadAdapter."""
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Property, QUrl, Slot, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from .models import DownloadListModel

class AppBridge(QObject):
    actionRejected = Signal(str)

    def __init__(self):
        super().__init__()
        self._download_model = DownloadListModel(self)

    @Property(str, constant=True)
    def appName(self): return "ADM"

    @Property(str, constant=True)
    def versionLabel(self): return "6.54 · QML Preview"

    @Property(str, constant=True)
    def connectionState(self): return "Preview mode — backend not connected"

    @Property(QObject, constant=True)
    def downloadModel(self): return self._download_model

    @Slot(str)
    def pause(self, task_id): self.actionRejected.emit("Preview mode: download backend is not connected.")

    @Slot(str)
    def resume(self, task_id): self.actionRejected.emit("Preview mode: download backend is not connected.")

    @Slot(str)
    def cancel(self, task_id): self.actionRejected.emit("Preview mode: download backend is not connected.")

    @Slot(str)
    def retry(self, task_id): self.actionRejected.emit("Preview mode: download backend is not connected.")

    @Property(int, constant=True)
    def activeDownloads(self): return 0

    @Property(str, constant=True)
    def totalSpeed(self): return "—"

    @Property(int, constant=True)
    def completedDownloads(self): return 0

def main():
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ADM QML Preview")
    app.setOrganizationName("ADM")
    engine = QQmlApplicationEngine()
    bridge = AppBridge()
    engine.rootContext().setContextProperty("appBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("Main.qml"))))
    if not engine.rootObjects(): return 1
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
