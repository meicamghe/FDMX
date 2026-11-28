"""Experimental Qt Quick shell for ADM/GNS Downloader.

This entry point remains isolated from the production QWidget app. It exposes
an empty, typed download model as the future QML/backend integration boundary.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .models import DownloadListModel


class AppBridge(QObject):
    """Narrow QObject facade exposed to QML."""

    def __init__(self) -> None:
        super().__init__()
        self._app_name = "ADM"
        self._version = "6.54 · QML Preview"
        self._connection_state = "Download backend not connected"
        self._download_model = DownloadListModel(self)

    @Property(str, constant=True)
    def appName(self) -> str:
        return self._app_name

    @Property(str, constant=True)
    def versionLabel(self) -> str:
        return self._version

    @Property(str, constant=True)
    def connectionState(self) -> str:
        return self._connection_state

    @Property(QObject, constant=True)
    def downloadModel(self) -> QObject:
        return self._download_model


def main() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ADM QML Preview")
    app.setOrganizationName("ADM")

    engine = QQmlApplicationEngine()
    bridge = AppBridge()
    engine.rootContext().setContextProperty("appBridge", bridge)

    qml_file = Path(__file__).with_name("Main.qml")
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
