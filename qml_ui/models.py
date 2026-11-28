"""Typed Qt list model for normalized download snapshots."""
from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QByteArray

class DownloadListModel(QAbstractListModel):
    IdRole = int(Qt.ItemDataRole.UserRole) + 1
    FileNameRole = IdRole + 1
    StatusRole = IdRole + 2
    ProgressRole = IdRole + 3
    SpeedRole = IdRole + 4
    DownloadedRole = IdRole + 5
    TotalRole = IdRole + 6
    CategoryRole = IdRole + 7
    ScheduledAtRole = IdRole + 8
    KindRole = IdRole + 9
    _ROLE_NAMES = {
        IdRole: QByteArray(b"downloadId"), FileNameRole: QByteArray(b"fileName"),
        StatusRole: QByteArray(b"status"), ProgressRole: QByteArray(b"progress"),
        SpeedRole: QByteArray(b"speed"), DownloadedRole: QByteArray(b"downloaded"),
        TotalRole: QByteArray(b"total"), CategoryRole: QByteArray(b"category"),
        ScheduledAtRole: QByteArray(b"scheduledAt"), KindRole: QByteArray(b"kind"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def roleNames(self): return self._ROLE_NAMES.copy()
    def rowCount(self, parent: QModelIndex = QModelIndex()): return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid() or not 0 <= index.row() < len(self._rows): return None
        row = self._rows[index.row()]
        return {
            self.IdRole: row["download_id"], self.FileNameRole: row["file_name"],
            self.StatusRole: row["status"], self.ProgressRole: row["progress"],
            self.SpeedRole: row["speed"], self.DownloadedRole: row["downloaded"],
            self.TotalRole: row["total"], self.CategoryRole: row["category"],
            self.ScheduledAtRole: row["scheduled_at"], self.KindRole: row["kind"],
        }.get(role)

    def replace_downloads(self, snapshots: Iterable[Mapping[str, Any]]) -> None:
        normalized = []
        for item in snapshots:
            try: progress = max(0, min(100, int(item.get("progress", 0))))
            except (TypeError, ValueError, OverflowError): progress = 0
            try:
                downloaded, total = max(0, int(item.get("downloaded", 0))), max(0, int(item.get("total", 0)))
            except (TypeError, ValueError, OverflowError): downloaded, total = 0, 0
            normalized.append({
                "download_id": str(item.get("download_id", "")),
                "file_name": str(item.get("file_name", "Untitled download")),
                "status": str(item.get("status", "Unknown")), "progress": progress,
                "speed": str(item.get("speed_text", item.get("speed", "—"))),
                "downloaded": downloaded, "total": total,
                "category": str(item.get("category", "")),
                "scheduled_at": str(item.get("scheduled_at", "")),
                "kind": str(item.get("kind", "http")),
            })
        # Polling the legacy controller should not reset the view when no
        # observable role changed; otherwise QML loses selection/scroll state.
        if normalized == self._rows:
            return
        self.beginResetModel()
        self._rows = normalized
        self.endResetModel()
