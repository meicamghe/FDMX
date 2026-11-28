"""Qt-thread-affine adapter between the legacy FDMX controller and QML."""
from __future__ import annotations

from typing import Any
import datetime
import urllib.parse
from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot
from .models import DownloadListModel

_ACTIVE = {"Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding", "Canceling"}


def _nonnegative(value: Any) -> float:
    try:
        result = float(value or 0)
        return result if result >= 0 else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _speed_text(value: float) -> str:
    amount = value
    unit = "B/s"
    for candidate in ("B/s", "KB/s", "MB/s", "GB/s"):
        unit = candidate
        if amount < 1024 or candidate == "GB/s":
            break
        amount /= 1024
    return f"{amount:.1f} {unit}"


def _task_snapshot(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    downloaded, total = _nonnegative(task.get("downloaded")), _nonnegative(task.get("total"))
    progress = min(100, int(downloaded * 100 / total)) if total else (100 if task.get("status") == "Completed" else 0)
    speed = _nonnegative(task.get("speed"))
    return {
        "download_id": str(task_id), "file_name": str(task.get("name") or "Download"),
        "status": str(task.get("status") or "Unknown"), "progress": progress,
        "speed_text": _speed_text(speed), "downloaded": int(downloaded), "total": int(total),
        "category": str(task.get("category") or ""), "scheduled_at": str(task.get("scheduled_at") or ""),
        "kind": str(task.get("kind") or "http"),
    }


class FDMXDownloadAdapter(QObject):
    """Narrow GUI-thread facade; no imports from the monolithic production module."""

    changed = Signal()
    actionRejected = Signal(str)

    def __init__(self, controller: QObject, parent: QObject | None = None, interval_ms: int = 350):
        super().__init__(parent)
        if QThread.currentThread() != controller.thread():
            raise RuntimeError("Adapter must be created on the controller's GUI thread")
        self._controller = controller
        self._rows: list[dict[str, Any]] = []
        self._model = DownloadListModel(self)
        self._history: list[dict[str, Any]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(max(100, int(interval_ms)))
        self._timer.timeout.connect(self.refresh)
        self.refresh()
        self._timer.start()

    def _assert_gui_thread(self):
        if QThread.currentThread() != self._controller.thread():
            raise RuntimeError("Controller access outside its owning GUI thread")

    @Slot()
    def refresh(self):
        self._assert_gui_thread()
        tasks = getattr(self._controller, "tasks", {})
        self._rows = [_task_snapshot(tid, task) for tid, task in tasks.items() if isinstance(task, dict)]
        self._model.replace_downloads(self._rows)
        history = getattr(self._controller, "history", [])
        self._history = [{
            "file_name": str(item.get("name") or "Download"),
            "status": str(item.get("status") or "Unknown"),
            "completed_at": _nonnegative(item.get("completed_at")),
            "time": str(item.get("time") or ""),
            "size": int(_nonnegative(item.get("size", item.get("downloaded")))),
            "downloaded": int(_nonnegative(item.get("downloaded", item.get("size")))),
            "category": str(item.get("category") or ""),
            "error": "See the application log for details." if item.get("error") else "",
        } for item in history if isinstance(item, dict)]
        self.changed.emit()

    @Property(QObject, constant=True)
    def downloadModel(self): return self._model

    @Property(str, constant=True)
    def appName(self): return "ADM"

    @Property(str, constant=True)
    def versionLabel(self): return "6.53 · Experimental QML"

    @Property("QVariantList", notify=changed)
    def downloads(self): return list(self._rows)

    @Property("QVariantList", notify=changed)
    def history(self): return list(self._history[-200:])

    @Property("QVariantMap", notify=changed)
    def settings(self):
        self._assert_gui_thread()
        c = self._controller
        def widget_value(name, method):
            widget = getattr(c, name, None)
            getter = getattr(widget, method, None)
            try:
                return getter() if callable(getter) else None
            except RuntimeError:
                return None
        return {
            "maxDownloads": widget_value("max_downloads", "value"),
            "connectionsPerDownload": widget_value("parts_count", "value"),
            "speedLimitKbps": widget_value("speed_limit", "value"),
            "torrentUploadLimitKbps": widget_value("torrent_upload_limit", "value"),
            "proxyEnabled": widget_value("proxy_enabled", "isChecked"),
            "downloadFolder": widget_value("folder", "text"),
        }

    @Property(int, notify=changed)
    def activeDownloads(self): return sum(row["status"] in _ACTIVE for row in self._rows)

    @Property(int, notify=changed)
    def queuedDownloads(self): return sum(row["status"] == "Queued" for row in self._rows)

    @Property(int, notify=changed)
    def completedDownloads(self): return sum(row["status"] == "Completed" for row in self._rows)

    @Property(int, notify=changed)
    def scheduledDownloads(self): return sum(bool(row["scheduled_at"]) for row in self._rows)

    @Property(str, notify=changed)
    def totalSpeed(self):
        # Controller-owned task snapshots are read only on the GUI thread.
        self._assert_gui_thread()
        tasks = getattr(self._controller, "tasks", {})
        return _speed_text(sum(_nonnegative(task.get("speed")) for task in tasks.values() if isinstance(task, dict)))

    @Property(str, constant=True)
    def connectionState(self): return "Connected to legacy download engine"

    def _task(self, task_id):
        self._assert_gui_thread()
        return getattr(self._controller, "tasks", {}).get(task_id)

    @Slot(str)
    def queueDownload(self, url):
        """Submit a URL through the existing controller's real intake pipeline."""
        self._assert_gui_thread()
        value = str(url or "").strip()
        parsed = urllib.parse.urlsplit(value)
        is_magnet = value.lower().startswith("magnet:?")
        if not is_magnet and (parsed.scheme.lower() not in ("http", "https") or not parsed.netloc):
            self.actionRejected.emit("Enter a valid HTTP, HTTPS, YouTube, or magnet link.")
            return
        url_widget = getattr(self._controller, "url", None)
        folder_widget = getattr(self._controller, "folder", None)
        submit = getattr(self._controller, "add_download", None)
        if url_widget is None or not callable(getattr(url_widget, "setText", None)) or not callable(submit):
            self.actionRejected.emit("The legacy download intake is unavailable.")
            return
        folder = ""
        if folder_widget is not None and callable(getattr(folder_widget, "text", None)):
            folder = str(folder_widget.text() or "").strip()
        if not folder:
            self.actionRejected.emit("Choose a download folder in the existing settings first.")
            return
        before = set(getattr(self._controller, "tasks", {}).keys())
        previous_text = str(url_widget.text() or "") if callable(getattr(url_widget, "text", None)) else ""
        try:
            self._controller._pending_qml_handoff = True
            url_widget.setText(value)
            submit()
        except Exception:
            self.actionRejected.emit("The download engine could not accept this link.")
            return
        finally:
            # The Widgets entry field belongs to the legacy shell; do not leave
            # QML submissions in it or overwrite text the user was editing.
            try:
                url_widget.setText(previous_text)
            except Exception:
                pass
            try:
                self._controller._pending_qml_handoff = False
            except Exception:
                pass
        after = set(getattr(self._controller, "tasks", {}).keys())
        if after - before:
            self.refresh()
            return
        self.actionRejected.emit("The link was not added. It may already be in the queue or require attention in the legacy window.")

    @Slot(str)
    def pause(self, task_id):
        task = self._task(task_id)
        worker = task.get("worker") if task else None
        if not task or worker is None or task.get("status") not in _ACTIVE:
            self.actionRejected.emit("This download cannot be paused.")
            return
        try:
            worker.pause()
        except Exception:
            self.actionRejected.emit("The download worker could not be paused.")
            return
        task["status"] = "Paused"
        try:
            self._controller.save_tasks()
        except Exception:
            self.actionRejected.emit("Download paused, but its state could not be saved.")
        self.refresh()

    @Slot(str)
    def resume(self, task_id):
        task = self._task(task_id)
        worker = task.get("worker") if task else None
        if not task or worker is None or task.get("status") != "Paused":
            self.actionRejected.emit("This download cannot be resumed.")
            return
        try:
            worker.resume()
        except Exception:
            self.actionRejected.emit("The download worker could not be resumed.")
            return
        task["status"] = "Downloading"
        try:
            self._controller.save_tasks()
        except Exception:
            self.actionRejected.emit("Download resumed, but its state could not be saved.")
        self.refresh()

    @Slot(str)
    def cancel(self, task_id):
        if self._task(task_id) is None:
            self.actionRejected.emit("Download not found.")
            return
        try:
            self._controller.cancel_task(task_id)
        except Exception:
            self.actionRejected.emit("The download could not be canceled.")
            return
        self.refresh()

    def _refresh_schedule_view(self):
        refresh = getattr(self._controller, "refresh_schedule_table", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    @Slot(str, str)
    def setSchedule(self, task_id, scheduled_at):
        task = self._task(task_id)
        if not task:
            self.actionRejected.emit("Download not found.")
            return
        if task.get("status") != "Queued":
            self.actionRejected.emit("Only queued downloads can be scheduled.")
            return
        try:
            selected = datetime.datetime.fromisoformat(str(scheduled_at).strip())
            if selected.timestamp() <= datetime.datetime.now().timestamp():
                raise ValueError("time is not in the future")
        except (TypeError, ValueError, OverflowError):
            self.actionRejected.emit("Enter a valid future date and time in ISO format.")
            return
        previous = task.get("scheduled_at", "")
        task["scheduled_at"] = selected.isoformat()
        try:
            self._controller.save_tasks()
        except Exception:
            task["scheduled_at"] = previous
            self.actionRejected.emit("The schedule could not be saved.")
            return
        self._refresh_schedule_view()
        self.refresh()

    @Slot(str)
    def clearSchedule(self, task_id):
        task = self._task(task_id)
        if not task:
            self.actionRejected.emit("Download not found.")
            return
        previous = task.get("scheduled_at", "")
        task["scheduled_at"] = ""
        try:
            self._controller.save_tasks()
        except Exception:
            task["scheduled_at"] = previous
            self.actionRejected.emit("The schedule could not be cleared.")
            return
        self._refresh_schedule_view()
        self.refresh()

    @Slot(str)
    def startNow(self, task_id):
        task = self._task(task_id)
        if not task:
            self.actionRejected.emit("Download not found.")
            return
        if task.get("status") != "Queued":
            self.actionRejected.emit("Only queued downloads can be started now.")
            return
        previous = task.get("scheduled_at", "")
        task["scheduled_at"] = ""
        try:
            self._controller.save_tasks()
            self._controller.schedule_downloads()
        except Exception:
            task["scheduled_at"] = previous
            self.actionRejected.emit("The download could not be started now.")
        self._refresh_schedule_view()
        self.refresh()

    @Slot(str)
    def retry(self, task_id):
        task = self._task(task_id)
        if not task or task.get("status") not in ("Failed", "Canceled"):
            self.actionRejected.emit("Only failed or canceled downloads can be retried.")
            return
        task.update({"status": "Queued", "downloaded": 0, "total": 0, "speed": 0.0, "eta": -1.0, "path": "", "worker": None})
        try:
            self._controller.save_tasks()
            self._controller.schedule_downloads()
        except Exception:
            self.actionRejected.emit("Retry was queued, but the download scheduler failed.")
        self.refresh()
