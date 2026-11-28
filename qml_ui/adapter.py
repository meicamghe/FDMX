"""Qt-thread-affine adapter between the legacy FDMX controller and QML."""
from __future__ import annotations

from typing import Any
from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot

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
        history = getattr(self._controller, "history", [])
        self._history = [{
            "file_name": str(item.get("name") or "Download"),
            "status": str(item.get("status") or "Unknown"),
            "completed_at": _nonnegative(item.get("completed_at")),
            "downloaded": int(_nonnegative(item.get("downloaded"))),
            "category": str(item.get("category") or ""),
        } for item in history if isinstance(item, dict)]
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def downloads(self): return list(self._rows)

    @Property("QVariantList", notify=changed)
    def history(self): return list(self._history[-200:])

    @Property(int, notify=changed)
    def activeDownloads(self): return sum(row["status"] in _ACTIVE for row in self._rows)

    @Property(int, notify=changed)
    def queuedDownloads(self): return sum(row["status"] == "Queued" for row in self._rows)

    @Property(int, notify=changed)
    def completedDownloads(self): return sum(row["status"] == "Completed" for row in self._rows)

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
    def pause(self, task_id):
        task = self._task(task_id)
        worker = task.get("worker") if task else None
        if not task or worker is None or task.get("status") not in _ACTIVE:
            self.actionRejected.emit("This download cannot be paused.")
            return
        worker.pause()
        task["status"] = "Paused"
        self._controller.save_tasks()
        self.refresh()

    @Slot(str)
    def resume(self, task_id):
        task = self._task(task_id)
        worker = task.get("worker") if task else None
        if not task or worker is None or task.get("status") != "Paused":
            self.actionRejected.emit("This download cannot be resumed.")
            return
        worker.resume()
        task["status"] = "Downloading"
        self._controller.save_tasks()
        self.refresh()

    @Slot(str)
    def cancel(self, task_id):
        if self._task(task_id) is None:
            self.actionRejected.emit("Download not found.")
            return
        self._controller.cancel_task(task_id)
        self.refresh()

    @Slot(str)
    def retry(self, task_id):
        task = self._task(task_id)
        if not task or task.get("status") not in ("Failed", "Canceled"):
            self.actionRejected.emit("Only failed or canceled downloads can be retried.")
            return
        task.update({"status": "Queued", "downloaded": 0, "total": 0, "speed": 0.0, "eta": -1.0, "path": "", "worker": None})
        self._controller.save_tasks()
        self._controller.schedule_downloads()
        self.refresh()
