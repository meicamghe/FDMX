"""Experimental production launcher for the ADM Qt Quick interface.

The legacy FDMX controller remains the download engine. This entry point creates
one QApplication, hosts the QML window, and delegates shutdown to the controller
so its existing active-download confirmation and persistence logic is retained.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from FDMX_v6_50 import (
    FDMX,
    parse_gns_protocol_request,
)
from qml_ui.host import create_qml_window


def main() -> int:
    protocol_request = next(
        (
            parse_gns_protocol_request(arg)
            for arg in sys.argv[1:]
            if str(arg).lower().startswith("gnsdownloader://")
        ),
        None,
    )

    app = QApplication(sys.argv[:1])
    app.setApplicationName("ADM")
    app.setOrganizationName("ADM")

    controller = FDMX()
    controller.hide()
    engine, adapter, root = create_qml_window(controller)

    def handle_qml_close(event):
        accepted = controller.close()
        if not accepted:
            controller.show()
            event.accepted = False

    root.closing.connect(handle_qml_close)

    if protocol_request:
        if protocol_request["action"] == "download":
            QTimer.singleShot(
                0,
                lambda request=protocol_request: controller.add_download_from_browser(
                    request["url"], request.get("resolved_url", "")
                ),
            )
        elif protocol_request["action"] == "youtube":
            QTimer.singleShot(
                0,
                lambda request=protocol_request: controller.add_youtube_download_from_browser(
                    request["url"],
                    request["media_type"],
                    request["height"],
                    request.get("audio_bitrate", 0),
                ),
            )
        elif protocol_request["action"] == "website":
            QTimer.singleShot(
                0, lambda request=protocol_request: controller.open_website_from_browser(request["url"])
            )
        elif protocol_request["action"] == "open":
            QTimer.singleShot(0, root.raise_)

    if "--smoke-test" in sys.argv[1:]:
        QTimer.singleShot(1800, root.close)

    # Keep Python references alive for the full QML window lifetime.
    app._adm_qml_engine = engine
    app._adm_qml_adapter = adapter
    app._adm_legacy_controller = controller
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
