"""Typed Qt model used as the stable QML-facing download contract.

The model is intentionally backend-agnostic. The production downloader is not
connected yet; a future adapter can publish snapshots through replace_downloads.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QByteArray


class DownloadListModel(QAbstractListModel):
    """Read-only list model exposing normalized download rows to Qt Quick."""

    IdRole = int(Qt.ItemDataRole.UserRole) + 1
    FileNameRole = IdRole + 1
    StatusRole = IdRole + 2
    ProgressRole = IdRole + 3
    SpeedRole = IdRole + 4

    _ROLE_NAMES = {
        IdRole: QByteArray(b"downloadId"),
        FileNameRole: QByteArray(b"fileName"),
        StatusRole: QByteArray(b"status"),
        ProgressRole: QByteArray(b"progress"),
        SpeedRole: QByteArray(b"speed"),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def roleNames(self) -> dict[int, QByteArray]:
        return self._ROLE_NAMES.copy()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        return {
            self.IdRole: row["download_id"],
            self.FileNameRole: row["file_name"],
            self.StatusRole: row["status"],
            self.ProgressRole: row["progress"],
            self.SpeedRole: row["speed"],
        }.get(role)

    def replace_downloads(self, snapshots: Iterable[Mapping[str, Any]]) -> None:
        """Atomically replace visible rows with sanitized backend snapshots."""
        normalized: list[dict[str, Any]] = []
        for item in snapshots:
            try:
                progress = max(0, min(100, int(item.get("progress", 0))))
            except (TypeError, ValueError, OverflowError):
                progress = 0
            normalized.append({
                "download_id": str(item.get("download_id", "")),
                "file_name": str(item.get("file_name", "Untitled download")),
                "status": str(item.get("status", "Unknown")),
                "progress": progress,
                "speed": str(item.get("speed", "—")),
            })
        self.beginResetModel()
        self._rows = normalized
        self.endResetModel()
