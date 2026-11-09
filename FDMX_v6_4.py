import sys
import os
import re
import csv
import json
import time
import uuid
import hashlib
import mimetypes
import threading
import select
import tempfile
import shutil
import datetime
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.message import Message
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal, Qt, QSettings, QSize, QDateTime
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QMenu, QSpinBox,
    QDoubleSpinBox, QHeaderView, QAbstractItemView, QGroupBox, QFrame, QDialog,
    QDateTimeEdit, QCheckBox, QComboBox, QMenuBar, QVBoxLayout as VBoxLayout
)


APP_NAME = "GNS Downloader"
APP_VERSION = "6.4"
CONNECTIONS = 8
CHUNK_SIZE = 64 * 1024
READ_POLL_INTERVAL = 0.2  # seconds; pause responsiveness while waiting for network data


def open_url(request, timeout=60):
    return urllib.request.urlopen(request, timeout=timeout)

HISTORY_FILE = os.path.join(
    os.path.expanduser("~"), ".fdmx", "history.json"
)
TASKS_FILE = os.path.join(
    os.path.expanduser("~"), ".fdmx", "tasks.json"
)


class PersistentTempDirectory:
    """A task-scoped working directory that survives application restarts."""
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        os.makedirs(self.path, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def category_for_filename(filename):
    ext = os.path.splitext(filename.lower())[1]
    groups = {
        "Video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v"},
        "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
        "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt"},
        "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Programs": {".exe", ".msi", ".msix", ".apk", ".deb", ".rpm", ".dmg", ".iso"},
    }
    for category, extensions in groups.items():
        if ext in extensions:
            return category
    return "Other"


def format_bytes(value):
    value = max(0, int(value or 0))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TB"


def format_duration(seconds):
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def get_filename(response):
    disposition = response.headers.get("Content-Disposition", "")
    filename = None
    if disposition:
        msg = Message()
        msg["Content-Disposition"] = disposition
        filename = msg.get_filename()

    if not filename:
        parsed = urllib.parse.urlsplit(response.geturl())
        filename = os.path.basename(urllib.parse.unquote(parsed.path))

    if not filename:
        filename = "download"

    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).rstrip(" .")
    if not filename:
        filename = "download"

    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if not os.path.splitext(filename)[1]:
        extension = mimetypes.guess_extension(content_type)
        special = {
            "application/pdf": ".pdf",
            "application/zip": ".zip",
            "application/x-7z-compressed": ".7z",
            "application/x-rar-compressed": ".rar",
            "application/octet-stream": "",
            "application/vnd.microsoft.portable-executable": ".exe",
        }
        extension = special.get(content_type, extension)
        if extension:
            filename += extension

    stem = os.path.splitext(filename)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{i}" for i in range(1, 10))
    reserved.update(f"LPT{i}" for i in range(1, 10))
    if stem in reserved:
        filename = "_" + filename
    return filename


def unique_path(folder, filename):
    path = os.path.join(folder, filename)
    if not os.path.exists(path):
        return path
    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = os.path.join(folder, f"{name} ({counter}){ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


class RateLimiter:
    """A shared token bucket for all connections belonging to one download."""
    def __init__(self, bytes_per_second):
        self.rate = max(0, int(bytes_per_second))
        self.lock = threading.Lock()
        self.tokens = float(max(self.rate, CHUNK_SIZE))
        self.updated = time.monotonic()

    def acquire(self, amount, worker):
        if self.rate <= 0:
            return
        remaining = amount
        while remaining > 0:
            worker.wait_if_paused()
            if worker.cancel_event.is_set():
                raise InterruptedError("Download canceled")
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.updated
                self.tokens = min(
                    float(max(self.rate, CHUNK_SIZE)),
                    self.tokens + elapsed * self.rate
                )
                self.updated = now
                taken = min(remaining, int(self.tokens))
                if taken:
                    self.tokens -= taken
                    remaining -= taken
                    wait = 0
                else:
                    wait = min(0.2, max(0.01, remaining / self.rate))
            if wait:
                time.sleep(wait)


class DownloadWorker(QThread):
    progress = Signal(int, int, float, float)
    completed = Signal(str)
    failed = Signal(str)
    canceled = Signal()
    state = Signal(str)

    def __init__(self, task_id, url, folder, speed_limit_kbps=0):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.folder = folder
        self.speed_limit_kbps = speed_limit_kbps
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_event = threading.Event()
        # Active sockets are closed on Pause/Cancel to interrupt a blocked read.
        self._socket_lock = threading.Lock()
        self._active_sockets = set()
        self.downloaded = 0
        self.total = 0
        self.started_at = 0.0
        self.last_emit = 0.0
        self.last_bytes = 0
        self.current_speed = 0.0
        self.limiter = RateLimiter(speed_limit_kbps * 1024)

    def _interrupt_active_sockets(self):
        with self._socket_lock:
            sockets = list(self._active_sockets)
        for sock in sockets:
            try:
                sock.shutdown(2)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def register_socket(self, sock):
        if sock is None:
            return
        with self._socket_lock:
            self._active_sockets.add(sock)
            should_interrupt = not self.pause_event.is_set() or self.cancel_event.is_set()
        if should_interrupt:
            try:
                sock.shutdown(2)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def unregister_socket(self, sock):
        if sock is not None:
            with self._socket_lock:
                self._active_sockets.discard(sock)

    def pause(self):
        self.pause_event.clear()
        self._interrupt_active_sockets()
        with self.lock:
            self.current_speed = 0.0
            self.last_emit = time.monotonic()
            self.last_bytes = self.downloaded
            downloaded = self.downloaded
            total = self.total
        self.progress.emit(downloaded, total, 0.0, -1.0)
        self.state.emit("Paused")

    def resume(self):
        # Exclude the paused interval from the next speed calculation.
        with self.lock:
            self.current_speed = 0.0
            self.last_emit = time.monotonic()
            self.last_bytes = self.downloaded
        self.pause_event.set()
        self.state.emit("Downloading")

    def cancel(self):
        self.cancel_event.set()
        self.pause_event.set()
        self._interrupt_active_sockets()

    def wait_if_paused(self):
        while not self.pause_event.wait(0.2):
            if self.cancel_event.is_set():
                raise InterruptedError("Download canceled")
        if self.cancel_event.is_set():
            raise InterruptedError("Download canceled")

    def reset_progress(self, total=0):
        with self.lock:
            self.downloaded = 0
            self.total = total
            self.started_at = time.monotonic()
            self.last_emit = self.started_at
            self.last_bytes = 0
            self.current_speed = 0.0
        self.progress.emit(0, total, 0.0, -1.0)

    def update_progress(self, amount):
        with self.lock:
            self.downloaded += amount
            now = time.monotonic()
            elapsed = now - self.last_emit
            if elapsed >= 0.5:
                self.current_speed = (self.downloaded - self.last_bytes) / elapsed
                self.last_emit = now
                self.last_bytes = self.downloaded
            speed = self.current_speed
            downloaded = self.downloaded
            total = self.total
        eta = (total - downloaded) / speed if total > downloaded and speed > 0 else -1.0
        self.progress.emit(downloaded, total, speed, eta)

    def request(self, start=None, end=None):
        headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
        if start is not None:
            headers["Range"] = f"bytes={start}-{end}"
        req = urllib.request.Request(self.url, headers=headers)
        return urllib.request.urlopen(req, timeout=60)
        
    def get_response_socket(self, response):
        """Return urllib's underlying socket for readiness polling."""
        http_response = getattr(response, "fp", None)
        buffered = getattr(http_response, "fp", None)
        raw = getattr(buffered, "raw", None)
        sock = getattr(raw, "_sock", None)

        # Fallback for alternative urllib/http.client response layouts.
        if sock is None:
            raw = getattr(http_response, "raw", None)
            sock = getattr(raw, "_sock", None)
        return sock

    def read_chunk(self, response):
        reader = getattr(response, "read1", None)
        sock = self.get_response_socket(response)

        while True:
            self.wait_if_paused()

            # Do not call a blocking read while the server is idle. select() keeps
            # the socket blocking (unlike socket timeouts, which can poison the
            # buffered reader after a timeout). For TLS, pending() detects bytes
            # already decrypted inside the SSL layer.
            if sock is not None:
                try:
                    pending = sock.pending() if hasattr(sock, "pending") else 0
                    if not pending:
                        readable, _, _ = select.select(
                            [sock], [], [], READ_POLL_INTERVAL
                        )
                        if not readable:
                            continue
                except (OSError, ValueError):
                    # Let urllib report a real connection error through read().
                    pass

            self.wait_if_paused()
            if reader:
                return reader(CHUNK_SIZE)
            return response.read(CHUNK_SIZE)

    def download_part(self, index, start, end, temp_folder):
        """Download one byte range; after Pause, reconnect at the saved offset."""
        path = os.path.join(temp_folder, f"part_{index:02d}.tmp")
        expected = end - start + 1
        failures = 0

        while True:
            self.wait_if_paused()
            received = os.path.getsize(path) if os.path.exists(path) else 0
            if received >= expected:
                if received != expected:
                    raise RuntimeError(f"Part {index} is larger than expected")
                return path

            offset = start + received
            req = urllib.request.Request(
                self.url,
                headers={
                    "User-Agent": f"{APP_NAME}/{APP_VERSION}",
                    "Range": f"bytes={offset}-{end}",
                },
            )
            sock = None
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status != 206:
                        raise RuntimeError("Server stopped supporting HTTP Range")
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-{end}/"):
                        raise RuntimeError("Invalid Content-Range response")
                    sock = self.get_response_socket(response)
                    self.register_socket(sock)
                    mode = "ab" if received else "wb"
                    with open(path, mode) as output:
                        while True:
                            self.wait_if_paused()
                            chunk = self.read_chunk(response)
                            self.wait_if_paused()
                            if not chunk:
                                break
                            self.limiter.acquire(len(chunk), self)
                            self.wait_if_paused()
                            output.write(chunk)
                            output.flush()
                            received += len(chunk)
                            self.update_progress(len(chunk))
                failures = 0
            except InterruptedError:
                raise
            except Exception:
                # Closing the socket is the mechanism that interrupts a blocked
                # urllib read. A pause is not a failed download: wait, then Range-resume.
                if self.cancel_event.is_set():
                    raise InterruptedError("Download canceled")
                if not self.pause_event.is_set():
                    self.wait_if_paused()
                    continue
                failures += 1
                if failures > 3:
                    raise
                time.sleep(min(1.0 * failures, 3.0))
            finally:
                self.unregister_socket(sock)

            if os.path.exists(path):
                current = os.path.getsize(path)
                if current == expected:
                    return path
                if current > expected:
                    raise RuntimeError(f"Part {index} exceeded expected size")

    def download_single(self, destination):
        """Single-stream fallback. Pause interrupts the socket; resume restarts safely."""
        temp_path = destination + ".fdmx.tmp"
        self.reset_progress(0)
        failures = 0
        while True:
            self.wait_if_paused()
            sock = None
            try:
                with self.request() as response:
                    length = response.headers.get("Content-Length")
                    self.total = int(length) if length and length.isdigit() else 0
                    self.progress.emit(self.downloaded, self.total, 0.0, -1.0)
                    sock = self.get_response_socket(response)
                    self.register_socket(sock)
                    # Without HTTP Range support we must restart this stream from
                    # byte zero after a pause; never append a duplicate prefix.
                    with open(temp_path, "wb") as output:
                        if self.downloaded:
                            with self.lock:
                                self.downloaded = 0
                                self.last_bytes = 0
                                self.last_emit = time.monotonic()
                            self.progress.emit(0, self.total, 0.0, -1.0)
                        while True:
                            self.wait_if_paused()
                            chunk = self.read_chunk(response)
                            self.wait_if_paused()
                            if not chunk:
                                break
                            self.limiter.acquire(len(chunk), self)
                            self.wait_if_paused()
                            output.write(chunk)
                            output.flush()
                            self.update_progress(len(chunk))
                failures = 0
                if self.total and self.downloaded != self.total:
                    raise RuntimeError("Downloaded size does not match Content-Length")
                os.replace(temp_path, destination)
                return
            except InterruptedError:
                raise
            except Exception:
                if self.cancel_event.is_set():
                    raise InterruptedError("Download canceled")
                if not self.pause_event.is_set():
                    self.wait_if_paused()
                    continue
                failures += 1
                if failures > 3:
                    raise
                time.sleep(min(1.0 * failures, 3.0))
            finally:
                self.unregister_socket(sock)

    def download_multi(self, destination, total):
        self.reset_progress(total)
        parts_count = min(CONNECTIONS, total)
        ranges = []
        for index in range(parts_count):
            start = (total * index) // parts_count
            end = (total * (index + 1)) // parts_count - 1
            ranges.append((index, start, end))

        with PersistentTempDirectory(os.path.join(self.folder, f".fdmx_{self.task_id}.parts")) as temp_folder:
            existing_bytes = sum(
                min(os.path.getsize(os.path.join(temp_folder, f"part_{i:02d}.tmp")), end - start + 1)
                for i, start, end in ranges
                if os.path.isfile(os.path.join(temp_folder, f"part_{i:02d}.tmp"))
            )
            with self.lock:
                self.downloaded = existing_bytes
                self.last_bytes = existing_bytes
                self.last_emit = time.monotonic()
            self.progress.emit(existing_bytes, total, 0.0, -1.0)
            with ThreadPoolExecutor(max_workers=parts_count) as executor:
                futures = [
                    executor.submit(self.download_part, i, start, end, temp_folder)
                    for i, start, end in ranges
                ]
                part_paths = [future.result() for future in futures]

            self.wait_if_paused()
            temp_output = destination + ".fdmx.tmp"
            try:
                with open(temp_output, "wb") as output:
                    for part_path in part_paths:
                        with open(part_path, "rb") as part:
                            while True:
                                chunk = part.read(CHUNK_SIZE)
                                if not chunk:
                                    break
                                output.write(chunk)
                if os.path.getsize(temp_output) != total:
                    raise RuntimeError("Final file size mismatch")
                os.replace(temp_output, destination)
            finally:
                if os.path.exists(temp_output):
                    os.remove(temp_output)

    def run(self):
        destination = None
        try:
            self.state.emit("Checking server")
            self.wait_if_paused()
            with self.request(0, 0) as probe:
                filename = get_filename(probe)
                content_range = probe.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes 0-0/(\d+)", content_range)
                supported = probe.status == 206 and match is not None
                total = int(match.group(1)) if match else 0
                probe.read(1)
            self.wait_if_paused()

            os.makedirs(self.folder, exist_ok=True)
            destination = unique_path(self.folder, filename)

            last_error = None
            for attempt in range(3):
                if self.cancel_event.is_set():
                    raise InterruptedError("Download canceled")
                try:
                    if supported and total > 1:
                        self.download_multi(destination, total)
                    else:
                        self.download_single(destination)
                    self.progress.emit(100, self.total, self.current_speed, 0.0)
                    self.state.emit("Completed")
                    parts_dir = os.path.join(self.folder, f".fdmx_{self.task_id}.parts")
                    if os.path.isdir(parts_dir):
                        shutil.rmtree(parts_dir, ignore_errors=True)
                    self.completed.emit(destination)
                    return
                except InterruptedError:
                    raise
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        self.state.emit(f"Retrying ({attempt + 1}/2)")
                        time.sleep(1.0 + attempt)
            raise RuntimeError(str(last_error))
        except InterruptedError:
            self.state.emit("Canceled")
            self.canceled.emit()
        except Exception as exc:
            self.state.emit("Failed")
            self.failed.emit(str(exc))




class TorrentWorker(QThread):
    """libtorrent-backed worker; continues seeding and honors an upload cap."""
    progress = Signal(int, int, float, float)
    failed = Signal(str)
    canceled = Signal()
    state = Signal(str)
    def __init__(self, task_id, source, folder, upload_limit_kbps=0):
        super().__init__()
        self.task_id, self.source, self.folder = task_id, source, folder
        self.upload_limit_kbps = max(0, int(upload_limit_kbps))
        self.stop_event = threading.Event()
        self._pause_lock = threading.Lock()
        self._pause_requested = False
        self.handle = None
        self.session = None
    def pause(self):
        with self._pause_lock:
            self._pause_requested = True
            handle = self.handle
        if handle:
            try: handle.pause()
            except Exception: pass
        self.state.emit("Paused")
    def resume(self):
        with self._pause_lock:
            self._pause_requested = False
            handle = self.handle
        if handle:
            try: handle.resume()
            except Exception: pass
        self.state.emit("Downloading")
    def cancel(self):
        self.stop_event.set()
        with self._pause_lock:
            handle = self.handle
        if handle:
            try: handle.pause()
            except Exception: pass
    def set_upload_limit(self, kbps):
        self.upload_limit_kbps = max(0, int(kbps))
    def run(self):
        try:
            import libtorrent as lt
            os.makedirs(self.folder, exist_ok=True)
            self.state.emit("Checking metadata")
            self.session = lt.session()
            self.session.apply_settings({"enable_dht": True, "enable_lsd": True, "enable_upnp": True, "enable_natpmp": True})
            if self.source.lower().startswith("magnet:"):
                params = lt.parse_magnet_uri(self.source)
                params.save_path = self.folder
            else:
                params = lt.add_torrent_params()
                params.ti = lt.torrent_info(self.source)
                params.save_path = self.folder
            self.handle = self.session.add_torrent(params)
            while not self.stop_event.is_set():
                with self._pause_lock:
                    paused = self._pause_requested
                if paused:
                    try: self.handle.pause()
                    except Exception: pass
                    self.state.emit("Paused")
                else:
                    try: self.handle.resume()
                    except Exception: pass
                    self.handle.set_upload_limit(self.upload_limit_kbps * 1024 if self.upload_limit_kbps else -1)
                    st = self.handle.status()
                    total, done, rate = int(st.total_wanted), int(st.total_wanted_done), float(st.download_rate)
                    eta = (total - done) / rate if rate > 0 and total > done else -1.0
                    self.progress.emit(done, total, rate, eta)
                    self.state.emit("Seeding" if st.is_seeding else "Downloading")
                time.sleep(0.6)
            if self.session and self.handle:
                try: self.session.remove_torrent(self.handle)
                except Exception: pass
            self.canceled.emit()
        except Exception as exc:
            if self.stop_event.is_set(): self.canceled.emit()
            else: self.failed.emit(f"Torrent error: {exc}")


class PartsDialog(QDialog):
    """Inspect the byte ranges used by one download."""
    def __init__(self, parent, task, connections=CONNECTIONS):
        super().__init__(parent)
        self.setWindowTitle("Download segments — " + task.get("name", "Download"))
        self.resize(760, 390)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("SEGMENTS  •  " + task.get("name", "Download")))
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Segment", "Byte range", "Downloaded", "Expected", "State"])
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col in (0, 2, 3, 4):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(table, 1)
        total = int(task.get("total") or 0)
        task_id = task.get("id", "")
        parts_dir = os.path.join(task.get("folder", ""), ".fdmx_" + task_id + ".parts")
        final_path = task.get("path", "")
        completed = task.get("status") == "Completed" and final_path and os.path.isfile(final_path)
        if completed:
            total = os.path.getsize(final_path)
        if total <= 0:
            layout.addWidget(QLabel("Segment information will be available after the server check."))
        else:
            count = min(connections, total)
            table.setRowCount(count)
            for index in range(count):
                start = (total * index) // count
                end = (total * (index + 1)) // count - 1
                expected = end - start + 1
                part_path = os.path.join(parts_dir, "part_%02d.tmp" % index)
                received = expected if completed else (min(os.path.getsize(part_path), expected) if os.path.isfile(part_path) else 0)
                state = "Completed" if received == expected else ("Downloading" if received else "Waiting")
                values = ["#%d" % (index + 1), "%s – %s" % (format_bytes(start), format_bytes(end)),
                          format_bytes(received), format_bytes(expected), state]
                for col, value in enumerate(values):
                    table.setItem(index, col, QTableWidgetItem(value))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        self.setStyleSheet("""
            QDialog { background:#111c30; color:#e8f1ff; }
            QTableWidget { background:#17263e; alternate-background-color:#1c304e; color:#e6efff; gridline-color:#304867; border:1px solid #46648d; }
            QHeaderView::section { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #42669b,stop:1 #203959); color:white; padding:9px; font-weight:700; }
            QPushButton { color:white; padding:8px 22px; border-radius:7px; border-top:1px solid #85b9ef; border-bottom:3px solid #0a1423; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #3976b8,stop:1 #21436f); }
        """)

class DraggableTitleBar(QWidget):
    """Frameless-window title area that can be dragged with the mouse."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class FDMX(QWidget):
    browser_download_requested = Signal(str)

    def __init__(self):
        super().__init__()
        # Use the application's own title-bar controls; hide the native Windows frame buttons.
        self.setWindowFlags(Qt.Window)
        self.setWindowTitle(f"{APP_NAME}  •  Download Manager {APP_VERSION}")
        self.setWindowIcon(self.create_app_icon())
        self.resize(1080, 680)
        self.setMinimumSize(820, 520)
        self.tasks = {}
        self.workers = {}
        self.history = []
        self._loading = False
        self._post_action_armed = False
        self._post_action_done = False
        self._session_task_ids = set()
        self.current_filter = "All downloads"
        self.search_query = ""
        self.load_history()
        self.load_tasks()
        self.build_ui()
        self.load_preferences()
        self.browser_download_requested.connect(self.add_download_from_browser)
        self.start_browser_bridge()
        self.refresh_table()
        self.scheduler_timer = self.startTimer(400)
        self.start_queue()

    def create_app_icon(self):
        pixmap = QPixmap(256, 256)
        pixmap.fill(QColor("#030303"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        # Deep black rounded tile with a subtle metallic edge.
        tile = QLinearGradient(0, 0, 0, 256)
        tile.setColorAt(0.0, QColor("#242424"))
        tile.setColorAt(0.48, QColor("#090909"))
        tile.setColorAt(1.0, QColor("#000000"))
        painter.setBrush(tile)
        painter.drawRoundedRect(8, 8, 240, 240, 48, 48)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(110, 110, 110, 105))
        painter.drawRoundedRect(9, 9, 238, 238, 47, 47)

        font = QFont("Inter", 178, QFont.Black)
        painter.setFont(font)
        rect = pixmap.rect().adjusted(0, -5, 0, 0)

        # Soft burgundy glow and depth behind the letter.
        painter.setPen(QColor(255, 0, 0, 150))
        for offset in (7, 5, 3):
            painter.drawText(rect.translated(0, offset), Qt.AlignCenter, "G")
        painter.setPen(QColor("#4a0000"))
        painter.drawText(rect.translated(2, 4), Qt.AlignCenter, "G")

        # Bright glossy burgundy-to-red face with a light-catching upper edge.
        letter = QLinearGradient(0, 35, 0, 220)
        letter.setColorAt(0.0, QColor("#fff0f0"))
        letter.setColorAt(0.12, QColor("#ff5a5a"))
        letter.setColorAt(0.38, QColor("#ff1010"))
        letter.setColorAt(0.72, QColor("#d00000"))
        letter.setColorAt(1.0, QColor("#780000"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(letter)
        painter.drawText(rect, Qt.AlignCenter, "G")

        # Narrow glossy highlight across the upper portion of the G.
        painter.setPen(QColor(255, 220, 232, 175))
        painter.drawText(rect.translated(0, -2), Qt.AlignCenter, "G")
        painter.end()
        return QIcon(pixmap)

    def make_nav_icon(self, symbol):
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#ff1717"))
        painter.setFont(QFont("Inter", 17, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, symbol)
        painter.end()
        return QIcon(pixmap)
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def build_ui(self):
        """Build the compact classic interface; advanced options live in the top menus."""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)
        self.setStyleSheet("""
            QWidget { font-family: "Segoe UI", Arial, sans-serif; font-size: 9pt; }
            QLineEdit, QSpinBox, QDateTimeEdit, QComboBox { padding: 5px 7px; min-height: 22px; }
            QPushButton { padding: 5px 10px; min-height: 25px; }
            QPushButton:hover { background: #dff4e7; }
            QTableWidget { gridline-color: #d9d9d9; }
            QHeaderView::section { padding: 5px 7px; }
            QProgressBar { min-height: 12px; max-height: 12px; text-align: center; }
        """)

        self.menu_bar = QMenuBar(self)
        file_menu = self.menu_bar.addMenu("File")
        file_menu.addAction("Add download", lambda: self.url.setFocus())
        file_menu.addAction("Export download list (CSV)", self.export_csv)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        download_menu = self.menu_bar.addMenu("Download")
        for label, callback in (
            ("Start queue", self.start_queue), ("Pause selected", self.pause_selected),
            ("Resume selected", self.resume_selected), ("Cancel selected", self.cancel_selected),
            ("Retry selected", self.retry_selected), ("Remove selected", self.remove_selected),
        ):
            download_menu.addAction(label, callback)

        view_menu = self.menu_bar.addMenu("View")
        filter_menu = view_menu.addMenu("Show")
        self.nav_buttons = {}
        for label in ("All downloads", "In progress", "Queue", "Completed", "Failed"):
            filter_menu.addAction(label, lambda checked=False, name=label: self.set_filter(name))

        tools_menu = self.menu_bar.addMenu("Tools")
        tools_menu.addAction("Add torrent file…", self.add_torrent_file)
        tools_menu.addAction("Read URL from clipboard", self.paste_clipboard_url)
        tools_menu.addAction("Calculate SHA-256", self.calculate_hash)
        settings_menu = self.menu_bar.addMenu("Settings")
        settings_menu.addAction("Preferences…", self.open_settings_dialog)
        help_menu = self.menu_bar.addMenu("Help")
        help_menu.addAction("About FDMX", self.show_about)
        root.setMenuBar(self.menu_bar)

        top = QHBoxLayout()
        brand = QLabel(f"<b>G</b>  GNS Downloader  <span style='color:#777'>v{APP_VERSION}</span>")
        brand.setStyleSheet("font-size:13pt;")
        top.addWidget(brand)
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search downloads…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(240)
        self.search.textChanged.connect(self.set_search)
        top.addWidget(self.search)
        self.summary = QLabel("Active: 0 | Queued: 0 | Completed: 0")
        top.addWidget(self.summary)
        root.addLayout(top)

        toolbar = QHBoxLayout()
        for label, callback in (
            ("Add URL", lambda: self.url.setFocus()), ("Start", self.start_queue),
            ("Pause", self.pause_selected), ("Resume", self.resume_selected),
            ("Cancel", self.cancel_selected), ("Remove", self.remove_selected),
            ("Open folder", self.open_folder),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        entry = QGridLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste HTTP, HTTPS, or magnet link here…")
        self.folder = QLineEdit(os.path.join(os.path.expanduser("~"), "Downloads"))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.select_folder)
        self.add_button = QPushButton("Add download")
        self.add_button.clicked.connect(self.add_download)
        self.clipboard_button = QPushButton("Clipboard")
        self.clipboard_button.setToolTip("Read a URL from the clipboard")
        self.clipboard_button.clicked.connect(self.paste_clipboard_url)
        self.add_torrent_button = QPushButton("Torrent…")
        self.add_torrent_button.clicked.connect(self.add_torrent_file)
        entry.addWidget(QLabel("URL:"), 0, 0)
        entry.addWidget(self.url, 0, 1, 1, 5)
        entry.addWidget(self.clipboard_button, 0, 6)
        entry.addWidget(QLabel("Save to:"), 1, 0)
        entry.addWidget(self.folder, 1, 1, 1, 4)
        entry.addWidget(browse, 1, 5)
        entry.addWidget(self.add_torrent_button, 1, 6)
        entry.addWidget(self.add_button, 1, 7)
        root.addLayout(entry)

        schedule_row = QHBoxLayout()
        self.schedule_enabled = QCheckBox("Schedule this download")
        self.schedule_time = QDateTimeEdit(QDateTime.currentDateTime())
        self.schedule_time.setCalendarPopup(True)
        self.schedule_time.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.schedule_time.setToolTip("The download remains queued until this local date and time")
        schedule_row.addWidget(self.schedule_enabled)
        schedule_row.addWidget(self.schedule_time)
        schedule_row.addStretch(1)
        root.addLayout(schedule_row)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("FDMX Preferences")
        self.settings_dialog.setMinimumWidth(430)
        settings_layout = QVBoxLayout(self.settings_dialog)
        settings_grid = QGridLayout()
        settings_grid.addWidget(QLabel("Maximum simultaneous downloads:"), 0, 0)
        self.max_downloads = QSpinBox()
        self.max_downloads.setRange(1, 16)
        self.max_downloads.setValue(8)
        settings_grid.addWidget(self.max_downloads, 0, 1)
        settings_grid.addWidget(QLabel("Speed limit per file (KB/s, 0 = unlimited):"), 1, 0)
        self.speed_limit = QSpinBox()
        self.speed_limit.setRange(0, 10_000_000)
        self.speed_limit.setValue(0)
        settings_grid.addWidget(self.speed_limit, 1, 1)
        settings_grid.addWidget(QLabel("Torrent upload limit (KB/s, 0 = unlimited):"), 2, 0)
        self.torrent_upload_limit = QSpinBox()
        self.torrent_upload_limit.setRange(0, 10_000_000)
        self.torrent_upload_limit.setValue(1)
        self.torrent_upload_limit.setToolTip("Maximum upload rate while seeding torrents")
        self.torrent_upload_limit.valueChanged.connect(self.update_torrent_upload_limit)
        settings_grid.addWidget(self.torrent_upload_limit, 2, 1)
        self.proxy_enabled = QCheckBox("Use HTTP/HTTPS proxy")
        settings_grid.addWidget(self.proxy_enabled, 3, 0, 1, 2)
        self.proxy_url = QLineEdit()
        self.proxy_url.setPlaceholderText("http://127.0.0.1:8080")
        settings_grid.addWidget(self.proxy_url, 4, 0, 1, 2)
        self.post_action_enabled = QCheckBox("After all downloads finish:")
        settings_grid.addWidget(self.post_action_enabled, 5, 0)
        self.post_action = QComboBox()
        self.post_action.addItem("Do nothing", "none")
        self.post_action.addItem("Shut down Windows", "shutdown")
        self.post_action.addItem("Log out of Windows", "logout")
        self.post_action.addItem("Hibernate Windows", "hibernate")
        settings_grid.addWidget(self.post_action, 5, 1)
        settings_layout.addLayout(settings_grid)
        settings_buttons = QHBoxLayout()
        settings_buttons.addStretch(1)
        settings_save = QPushButton("Save")
        settings_save.clicked.connect(self.save_and_close_settings)
        settings_close = QPushButton("Close")
        settings_close.clicked.connect(self.settings_dialog.accept)
        settings_buttons.addWidget(settings_save)
        settings_buttons.addWidget(settings_close)
        settings_layout.addLayout(settings_buttons)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "File / Progress", "Status", "Downloaded / Size",
            "Speed", "Time left"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)
        self.table.cellDoubleClicked.connect(self.open_or_show_download)

        self.details = QLabel("Select a download to view details. Double-click a row to inspect its segments.")
        self.details.setWordWrap(True)
        self.table.itemSelectionChanged.connect(self.update_details)
        root.addWidget(self.details)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        bottom = QHBoxLayout()
        self.hash_button = QPushButton("SHA-256")
        self.hash_button.clicked.connect(self.calculate_hash)
        self.export_button = QPushButton("Export CSV")
        self.export_button.clicked.connect(self.export_csv)
        bottom.addWidget(self.hash_button)
        bottom.addWidget(self.export_button)
        bottom.addStretch(1)
        root.addLayout(bottom)
        self.status = QLabel("Ready — add a URL to begin.")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.status)

    def open_settings_dialog(self):
        self.settings_dialog.exec()

    def save_and_close_settings(self):
        self.save_preferences()
        self.settings_dialog.accept()

    def show_about(self):
        QMessageBox.about(self, "About FDMX",
                          f"GNS Downloader / FDMX {APP_VERSION}\\nA lightweight download manager.")

    def set_filter(self, name):
        self.current_filter = name
        for key, button in self.nav_buttons.items():
            button.setChecked(key == name)
        self.refresh_table()

    def set_search(self, value):
        self.search_query = value.strip().lower()
        self.refresh_table()

    def visible_tasks(self):
        result = []
        for task_id, task in self.tasks.items():
            status = task.get("status", "")
            category = self.current_filter
            if category == "In progress" and status not in ("Downloading", "Checking server", "Retrying", "Paused"):
                continue
            if category == "Queue" and status != "Queued":
                continue
            if category == "Completed" and status != "Completed":
                continue
            if category == "Failed" and status not in ("Failed", "Canceled"):
                continue
            query = self.search_query
            if query and query not in task.get("name", "").lower() and query not in task.get("url", "").lower():
                continue
            result.append((task_id, task))
        return result

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row < 0:
            return

        self.table.setCurrentCell(row, 0)
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if not task:
            return

        status = task.get("status", "")
        active = status in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding")
        menu = QMenu(self)

        # Always show the four requested download actions.
        # Disable actions that do not apply to the selected task's current state.
        start_action = menu.addAction("Start download")
        start_action.setEnabled(status == "Queued")
        start_action.triggered.connect(self.start_queue)

        resume_action = menu.addAction("Resume download")
        resume_action.setEnabled(status == "Paused")
        resume_action.triggered.connect(self.resume_selected)

        cancel_action = menu.addAction("Cancel download")
        cancel_action.setEnabled(active)
        cancel_action.triggered.connect(self.cancel_selected)

        retry_action = menu.addAction("Retry download")
        retry_action.setEnabled(status in ("Failed", "Canceled"))
        retry_action.triggered.connect(self.retry_selected)

        menu.addSeparator()

        if status == "Completed":
            open_file_action = menu.addAction("Open file")
            open_file_action.setEnabled(bool(task.get("path") and os.path.isfile(task["path"])))
            open_file_action.triggered.connect(self.open_file)

            hash_action = menu.addAction("Calculate SHA-256")
            hash_action.setEnabled(bool(task.get("path") and os.path.isfile(task["path"])))
            hash_action.triggered.connect(self.calculate_hash)

        if menu.actions():
            menu.addSeparator()

        folder_action = menu.addAction("Open containing folder")
        folder_action.triggered.connect(self.open_folder)

        copy_url_action = menu.addAction("Copy download URL")
        copy_url_action.triggered.connect(
            lambda checked=False, value=task.get("url", ""): QApplication.clipboard().setText(value)
        )

        location = task.get("path") or task.get("folder", "")
        copy_location_action = menu.addAction("Copy save location")
        copy_location_action.setEnabled(bool(location))
        copy_location_action.triggered.connect(
            lambda checked=False, value=location: QApplication.clipboard().setText(value)
        )

        menu.addSeparator()
        remove_action = menu.addAction("Remove from list")
        remove_action.setEnabled(not active)
        remove_action.triggered.connect(self.remove_selected)

        menu.exec(self.table.viewport().mapToGlobal(position))

    def open_file(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        path = task.get("path") if task else ""
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, "Open file", "The downloaded file is not available.")
            return

        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            QMessageBox.warning(self, "Open file", str(exc))

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select download folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def paste_clipboard_url(self):
        value = QApplication.clipboard().text().strip()
        if value:
            self.url.setText(value)
            self.url.setFocus()
            self.status.setText("URL read from clipboard.")
        else:
            self.status.setText("Clipboard is empty.")


    def start_browser_bridge(self):
        """Local-only HTTP bridge used by the official Firefox and Chrome extensions."""
        window = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code, payload):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "null"))
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Vary", "Origin")
                self.end_headers()
                self.wfile.write(data)

            def _allowed_origin(self):
                origin = self.headers.get("Origin", "")
                return origin.startswith("moz-extension://") or origin.startswith("chrome-extension://")

            def do_OPTIONS(self):
                if not self._allowed_origin():
                    self._send(403, {"ok": False, "error": "Extension origin required"})
                    return
                self._send(204, {"ok": True})

            def do_GET(self):
                if self.path == "/health":
                    self._send(200, {"ok": True, "app": "FDMX", "version": APP_VERSION})
                else:
                    self._send(404, {"ok": False, "error": "Not found"})

            def do_POST(self):
                if self.path != "/download" or not self._allowed_origin():
                    self._send(403, {"ok": False, "error": "Not allowed"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 1 or length > 65536:
                        raise ValueError("Invalid request size")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    url = str(payload.get("url", "")).strip()
                    parsed = urllib.parse.urlsplit(url)
                    if parsed.scheme not in ("http", "https") or not parsed.netloc:
                        raise ValueError("Only HTTP and HTTPS links are supported")
                    window.browser_download_requested.emit(url)
                    self._send(202, {"ok": True, "message": "Added to FDMX queue"})
                except Exception as exc:
                    self._send(400, {"ok": False, "error": str(exc)})

            def log_message(self, fmt, *args):
                return

        try:
            self._browser_server = ThreadingHTTPServer(("127.0.0.1", 38471), Handler)
            self._browser_server.daemon_threads = True
            self._browser_thread = threading.Thread(target=self._browser_server.serve_forever, daemon=True)
            self._browser_thread.start()
        except OSError as exc:
            self._browser_server = None
            self.status.setText(f"Browser bridge unavailable: {exc}")

    def add_download_from_browser(self, url):
        """Queue a browser-submitted URL using the current download folder."""
        self.url.setText(url)
        self.add_download()

    def add_download(self):
        url = self.url.text().strip()
        folder = self.folder.text().strip()
        if url.lower().startswith("magnet:?"):
            self.add_torrent_source(url)
            self.url.clear()
            return
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid URL", "Enter a valid HTTP or HTTPS URL.")
            return
        if not folder:
            QMessageBox.warning(self, "Folder required", "Select a download folder.")
            return
        os.makedirs(folder, exist_ok=True)
        task_id = uuid.uuid4().hex
        self._session_task_ids.add(task_id)
        self.tasks[task_id] = {
            "id": task_id, "url": url, "folder": folder,
            "name": os.path.basename(urllib.parse.unquote(parsed.path)) or "Download",
            "status": "Queued", "downloaded": 0, "total": 0,
            "speed": 0.0, "eta": -1.0, "path": "",
            "worker": None, "history": False,
            "scheduled_at": self.schedule_time.dateTime().toString(Qt.ISODate) if self.schedule_enabled.isChecked() else "",
            "category": category_for_filename(os.path.basename(urllib.parse.unquote(parsed.path)) or "Download")
        }
        self._post_action_armed = True
        self._post_action_done = False
        self.save_tasks()
        self.url.clear()
        self.refresh_table()
        self.status.setText("Scheduled download added to queue." if self.schedule_enabled.isChecked() else "Added to queue.")
        self.start_queue()

    def add_torrent_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open torrent file", "", "Torrent files (*.torrent)")
        if path:
            self.add_torrent_source(path)
    def add_torrent_source(self, source):
        folder = self.folder.text().strip()
        if not folder:
            QMessageBox.warning(self, "Folder required", "Select a download folder.")
            return
        os.makedirs(folder, exist_ok=True)
        parsed = urllib.parse.urlsplit(source)
        name = urllib.parse.parse_qs(parsed.query).get("dn", ["Torrent download"])[0]
        if os.path.isfile(source):
            name = os.path.basename(source)
        task_id = uuid.uuid4().hex
        self._session_task_ids.add(task_id)
        self.tasks[task_id] = {
            "id": task_id, "url": source, "folder": folder, "name": name,
            "status": "Queued", "downloaded": 0, "total": 0, "speed": 0.0,
            "eta": -1.0, "path": "", "worker": None, "history": False,
            "kind": "torrent", "category": "Torrent", "upload_speed": 0.0,
            "scheduled_at": self.schedule_time.dateTime().toString(Qt.ISODate) if self.schedule_enabled.isChecked() else ""
        }
        self._post_action_armed = True
        self._post_action_done = False
        self.save_tasks()
        self.refresh_table()
        self.status.setText("Scheduled torrent added to queue." if self.schedule_enabled.isChecked() else "Torrent added to queue.")
        self.start_queue()
    def start_queue(self):
        self.schedule_downloads()

    def schedule_downloads(self):
        active = sum(1 for task in self.tasks.values() if task["status"] in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding"))
        capacity = self.max_downloads.value()
        if active >= capacity:
            return
        for task_id, task in list(self.tasks.items()):
            if active >= capacity:
                break
            if task["status"] != "Queued":
                continue
            scheduled_at = task.get("scheduled_at")
            if scheduled_at:
                try:
                    start_time = datetime.datetime.fromisoformat(scheduled_at)
                    if datetime.datetime.now().astimezone() < start_time.astimezone():
                        continue
                except (ValueError, TypeError):
                    task["scheduled_at"] = ""
            if task.get("kind") == "torrent":
                worker = TorrentWorker(task_id, task["url"], task["folder"], self.torrent_upload_limit.value())
            else:
                worker = DownloadWorker(task_id, task["url"], task["folder"], self.speed_limit.value())
            task["worker"] = worker
            self.workers[task_id] = worker
            worker.progress.connect(self.on_progress)
            worker.completed.connect(self.on_completed)
            worker.failed.connect(self.on_failed)
            worker.canceled.connect(self.on_canceled)
            worker.state.connect(lambda value, tid=task_id: self.on_state(tid, value))
            task["status"] = "Downloading"
            worker.start()
            active += 1
        self.refresh_table()
        self.check_after_download_action()

    def open_or_show_download(self, row, column):
        item = self.table.item(row, 0)
        task_id = item.data(Qt.UserRole) if item else None
        task = self.tasks.get(task_id) if task_id else None
        if not task:
            return
        self.table.setCurrentCell(row, 0)
        if task.get("status") == "Completed":
            self.open_file()
        else:
            PartsDialog(self, task).exec()

    def parts_tooltip(self, task):
        """Build a live hover summary of the download's parallel segments."""
        if task.get("kind") == "torrent":
            return "Torrent task\nHover details: torrent progress and seeding status are shown in the row."
        if task.get("status") == "Completed":
            return "Download completed\nDouble-click to open the downloaded file."
        total = int(task.get("total") or 0)
        count = min(CONNECTIONS, total) if total > 0 else CONNECTIONS
        if total <= 0:
            return (
                f"Download threads: {count}\n"
                "Waiting for server response; individual part sizes will appear after metadata is received."
            )
        parts_dir = os.path.join(task.get("folder", ""), ".fdmx_" + task.get("id", "") + ".parts")
        lines = [f"Download threads: {count}"]
        for index in range(count):
            start = (total * index) // count
            end = (total * (index + 1)) // count - 1
            expected = end - start + 1
            part_path = os.path.join(parts_dir, "part_%02d.tmp" % index)
            received = min(os.path.getsize(part_path), expected) if os.path.isfile(part_path) else 0
            state = "Complete" if received >= expected else ("Downloading" if received else "Waiting")
            lines.append(f"Part {index + 1}: {format_bytes(received)} / {format_bytes(expected)} — {state}")
        return "\n".join(lines)

    def selected_task(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def pause_selected(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if task and task.get("worker") and task["status"] in ("Downloading", "Checking server", "Retrying", "Checking metadata", "Seeding"):
            task["worker"].pause()
            task["status"] = "Paused"
            self.refresh_table()

    def resume_selected(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if task and task.get("worker") and task["status"] == "Paused":
            task["worker"].resume()
            task["status"] = "Downloading"
            self.refresh_table()

    def cancel_selected(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if not task:
            return
        if task["status"] == "Queued":
            task["status"] = "Canceled"
            self.save_history_entry(task)
        elif task.get("worker"):
            task["worker"].cancel()
        self.refresh_table()

    def retry_selected(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if not task or task["status"] not in ("Failed", "Canceled"):
            return
        task.update({
            "status": "Queued", "downloaded": 0, "total": 0,
            "speed": 0.0, "eta": -1.0, "path": "", "worker": None
        })
        self.schedule_downloads()
        self.refresh_table()

    def remove_selected(self):
        task_id = self.selected_task()
        if not task_id:
            return
        task = self.tasks.get(task_id)
        if task and task["status"] in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding"):
            QMessageBox.information(self, "Download active", "Cancel the active download before removing it.")
            return
        self.tasks.pop(task_id, None)
        self.save_tasks()
        self.refresh_table()

    def on_progress(self, downloaded, total, speed, eta):
        sender = self.sender()
        task_id = None
        for tid, worker in self.workers.items():
            if worker is sender:
                task_id = tid
                break
        if not task_id or task_id not in self.tasks:
            return
        task = self.tasks[task_id]
        task.update({
            "downloaded": downloaded, "total": total,
            "speed": speed, "eta": eta
        })
        self.update_row(task_id)

    def on_state(self, task_id, state):
        task = self.tasks.get(task_id)
        if task:
            worker = task.get("worker")
            if worker and hasattr(worker, "pause_event") and not worker.pause_event.is_set() and state != "Paused":
                return
            if worker and hasattr(worker, "_pause_requested") and worker._pause_requested and state != "Paused":
                return
            task["status"] = state
            self.save_tasks()
            self.update_row(task_id)

    def on_completed(self, path):
        task_id = self.sender().task_id
        task = self.tasks.get(task_id)
        if task:
            task.update({
                "status": "Completed", "path": path,
                "downloaded": os.path.getsize(path) if os.path.exists(path) else task["downloaded"],
                "speed": 0.0, "eta": 0.0, "worker": None
            })
            self.save_history_entry(task)
            self.refresh_table()
            self.status.setText(f"Completed: {path}")
        self.cleanup_worker(task_id)
        self.schedule_downloads()
        self.check_after_download_action()

    def on_failed(self, message):
        task_id = self.sender().task_id
        task = self.tasks.get(task_id)
        if task:
            task.update({"status": "Failed", "speed": 0.0, "eta": -1.0, "worker": None})
            self.save_history_entry(task, error=message)
            self.refresh_table()
            self.status.setText(f"Download failed: {message}")
        self.cleanup_worker(task_id)
        self.schedule_downloads()
        self.check_after_download_action()
        QMessageBox.warning(self, "Download failed", message)

    def on_canceled(self):
        task_id = self.sender().task_id
        task = self.tasks.get(task_id)
        if task:
            task.update({"status": "Canceled", "speed": 0.0, "eta": -1.0, "worker": None})
            self.save_history_entry(task)
            self.refresh_table()
        self.cleanup_worker(task_id)
        self.schedule_downloads()
        self.check_after_download_action()

    def cleanup_worker(self, task_id):
        worker = self.workers.pop(task_id, None)
        if worker:
            worker.deleteLater()

    def update_row(self, task_id):
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0) and self.table.item(row, 0).data(Qt.UserRole) == task_id:
                self.fill_row(row, self.tasks[task_id])
                break
        self.update_summary()

    def refresh_table(self):
        visible = self.visible_tasks()
        self.table.setRowCount(len(visible))
        for row, (task_id, task) in enumerate(visible):
            self.fill_row(row, task)
        self.update_summary()

    def fill_row(self, row, task):
        values = [
            task['name'], task['status'],
            f"{format_bytes(task['downloaded'])} / {format_bytes(task['total'])}" if task['total'] else format_bytes(task['downloaded']),
            format_bytes(task['speed']) + '/s',
            format_duration(task['eta'])
        ]
        hover_text = self.parts_tooltip(task)
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(hover_text)
            if col == 0:
                item.setData(Qt.UserRole, task['id'])
            if col in (2, 3, 4):
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)

        category = task.get('category') or category_for_filename(task['name'])
        type_icons = {'Video': '🎬', 'Audio': '🎵', 'Documents': '📄', 'Compressed': '📦', 'Programs': '💿', 'Other': '📁'}
        icon = type_icons.get(category, '📁')
        bar = QProgressBar()
        bar.setRange(0, 100)
        percent = int(task['downloaded'] * 100 / task['total']) if task['total'] else 0
        bar.setValue(min(100, percent))
        bar.setFormat(f'{min(100, percent)}%')
        bar.setToolTip(hover_text)
        name_label = QLabel(f"{icon}  {task['name']}")
        name_label.setStyleSheet('font-weight:600;padding-left:3px;')
        name_label.setToolTip(hover_text)
        file_cell = QWidget()
        file_layout = VBoxLayout(file_cell)
        file_layout.setContentsMargins(4, 3, 4, 3)
        file_layout.setSpacing(2)
        file_layout.addWidget(name_label)
        file_layout.addWidget(bar)
        self.table.setCellWidget(row, 0, file_cell)
        self.table.setRowHeight(row, 58)

    def update_details(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id) if task_id else None
        if not task:
            self.details.setText("Select a download to view its details.")
            return
        self.details.setText(
            f'{task.get("name", "Download")}  •  {task.get("category") or category_for_filename(task.get("name", ""))}  •  {task.get("status", "Unknown")}\n'
            f'URL: {task.get("url", "")}\n'
            f'Save location: {task.get("path") or task.get("folder", "")}\n'
            f'Downloaded: {format_bytes(task.get("downloaded", 0))} / {format_bytes(task.get("total", 0))}'
        )

    def update_summary(self):
        active = sum(1 for t in self.tasks.values() if t["status"] in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding"))
        queued = sum(1 for t in self.tasks.values() if t["status"] == "Queued")
        done = sum(1 for t in self.tasks.values() if t["status"] == "Completed")
        self.summary.setText(f"ACTIVE  {active}     QUEUED  {queued}     COMPLETED  {done}")

    def load_tasks(self):
        """Restore unfinished tasks; multipart byte ranges continue from saved part files."""
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
            for entry in saved:
                if not isinstance(entry, dict) or not entry.get("url") or not entry.get("folder"):
                    continue
                task_id = entry.get("id") or uuid.uuid4().hex
                if task_id in self.tasks:
                    continue
                status = entry.get("status", "Queued")
                if status in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding"):
                    status = "Queued"
                self.tasks[task_id] = {
                    "id": task_id, "url": entry["url"], "folder": entry["folder"],
                    "name": entry.get("name", "Download"), "status": status,
                    "downloaded": entry.get("downloaded", 0), "total": entry.get("total", 0),
                    "speed": 0.0, "eta": -1.0, "path": entry.get("path", ""),
                    "worker": None, "history": False,
                    "kind": entry.get("kind", "http"),
                    "scheduled_at": entry.get("scheduled_at", ""),
                    "category": entry.get("category") or category_for_filename(entry.get("name", ""))
                }
        except (OSError, ValueError, TypeError):
            pass

    def save_tasks(self):
        """Atomically persist resumable task metadata; part data is stored beside each download."""
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        saved = []
        for task in self.tasks.values():
            if task.get("status") in ("Completed", "Failed", "Canceled"):
                continue
            saved.append({key: task.get(key) for key in (
                "id", "url", "folder", "name", "status", "downloaded", "total", "path", "category", "kind", "scheduled_at"
            )})
        temp_path = TASKS_FILE + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(saved, file, ensure_ascii=False, indent=2)
            os.replace(temp_path, TASKS_FILE)
        except OSError as exc:
            self.status.setText(f"Could not save pending downloads: {exc}")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    def load_history(self):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                self.history = json.load(file)
            for entry in self.history[-100:]:
                if entry.get("status") == "Completed":
                    task_id = uuid.uuid4().hex
                    self.tasks[task_id] = {
                        "id": task_id, "url": entry.get("url", ""),
                        "folder": entry.get("folder", ""),
                        "name": entry.get("name", "Download"),
                        "status": "Completed", "downloaded": entry.get("size", 0),
                        "total": entry.get("size", 0), "speed": 0.0,
                        "eta": 0.0, "path": entry.get("path", ""),
                        "worker": None, "history": True
                    }
        except (OSError, ValueError, TypeError):
            self.history = []

    def save_history_entry(self, task, error=""):
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "url": task["url"], "folder": task["folder"],
            "name": task["name"], "status": task["status"],
            "path": task.get("path", ""),
            "size": task.get("downloaded", 0), "error": error
        }
        self.history.append(entry)
        self.history = self.history[-500:]
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as file:
                json.dump(self.history, file, ensure_ascii=False, indent=2)
        except OSError as exc:
            self.status.setText(f"Could not save history: {exc}")

    def load_preferences(self):
        """Restore user preferences saved by the previous session."""
        self.settings = QSettings("GNS", "FDMX")
        self.max_downloads.setValue(self.settings.value("max_downloads", 8, type=int))
        self.speed_limit.setValue(self.settings.value("speed_limit", 0, type=int))
        self.torrent_upload_limit.setValue(self.settings.value("torrent_upload_limit", 1, type=int))
        default_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        self.folder.setText(self.settings.value("download_folder", default_folder, type=str))
        self.max_downloads.valueChanged.connect(self.save_preferences)
        self.speed_limit.valueChanged.connect(self.save_preferences)
        self.torrent_upload_limit.valueChanged.connect(self.save_preferences)
        self.folder.editingFinished.connect(self.save_preferences)
        self.proxy_enabled.setChecked(self.settings.value("proxy_enabled", False, type=bool))
        self.proxy_url.setText(self.settings.value("proxy_url", "", type=str))
        self.post_action_enabled.setChecked(self.settings.value("post_action_enabled", False, type=bool))
        action = self.settings.value("post_action", "none", type=str)
        self.post_action.setCurrentIndex(max(0, self.post_action.findData(action)))
        self.proxy_enabled.toggled.connect(self.save_preferences)
        self.proxy_url.editingFinished.connect(self.save_preferences)
        self.post_action_enabled.toggled.connect(self.save_preferences)
        self.post_action.currentIndexChanged.connect(self.save_preferences)
        self.apply_proxy_settings()

    def save_preferences(self):
        """Persist preferences without touching queued or active download data."""
        if not hasattr(self, "settings"):
            return
        self.settings.setValue("max_downloads", self.max_downloads.value())
        self.settings.setValue("speed_limit", self.speed_limit.value())
        self.settings.setValue("torrent_upload_limit", self.torrent_upload_limit.value())
        self.settings.setValue("download_folder", self.folder.text().strip())
        self.settings.setValue("proxy_enabled", self.proxy_enabled.isChecked())
        self.settings.setValue("proxy_url", self.proxy_url.text().strip())
        self.settings.setValue("post_action_enabled", self.post_action_enabled.isChecked())
        self.settings.setValue("post_action", self.post_action.currentData())
        self.settings.sync()
        self.apply_proxy_settings()

    def apply_proxy_settings(self):
        """Apply the optional HTTP/HTTPS proxy to urllib-based downloads."""
        if self.proxy_enabled.isChecked() and self.proxy_url.text().strip():
            proxy = self.proxy_url.text().strip()
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            urllib.request.install_opener(urllib.request.build_opener(handler))
        else:
            urllib.request.install_opener(urllib.request.build_opener())

    def check_after_download_action(self):
        if not self._post_action_armed or self._post_action_done or not self.post_action_enabled.isChecked():
            return
        active_states = ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding")
        session_tasks = [self.tasks[tid] for tid in self._session_task_ids if tid in self.tasks]
        if not session_tasks:
            return
        if any(t.get("status") in active_states or t.get("status") == "Queued" for t in session_tasks):
            return
        if not any(t.get("status") == "Completed" for t in session_tasks):
            return
        action = self.post_action.currentData()
        if action == "none":
            self._post_action_done = True
            return
        if os.name != "nt":
            self.status.setText("Post-download power actions are available on Windows only.")
            self._post_action_done = True
            return
        import subprocess
        commands = {
            "shutdown": ["shutdown", "/s", "/t", "30"],
            "logout": ["shutdown", "/l"],
            "hibernate": ["shutdown", "/h"]
        }
        command = commands.get(action)
        if command:
            self._post_action_done = True
            self.status.setText("All downloads finished. Windows action will run shortly.")
            subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def update_torrent_upload_limit(self, value):
        for worker in self.workers.values():
            if isinstance(worker, TorrentWorker):
                worker.set_upload_limit(value)
    def export_csv(self):
        """Export the current download list as a UTF-8 CSV report."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export downloads", "GNS-Downloader-Report.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return
        fields = ["name", "category", "status", "downloaded", "total", "url", "path", "folder", "kind"]
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as output:
                writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for task in self.tasks.values():
                    row = {key: task.get(key, "") for key in fields}
                    row["category"] = row["category"] or category_for_filename(row["name"])
                    writer.writerow(row)
            QMessageBox.information(self, "Export complete", f"CSV report saved to:\n{path}")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def calculate_hash(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        path = task.get("path") if task else ""
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, "SHA-256", "Select a completed download first.")
            return
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
            value = digest.hexdigest()
            QMessageBox.information(self, "SHA-256", f"{value}\n\n{path}")
        except OSError as exc:
            QMessageBox.warning(self, "SHA-256", str(exc))

    def open_folder(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if not task:
            return
        path = task.get("path") if task.get("path") and os.path.exists(task["path"]) else task["folder"]
        if os.path.isdir(path):
            target = path
        else:
            target = os.path.dirname(path)
        if os.name == "nt":
            os.startfile(target)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", target])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", target])

    def timerEvent(self, event):
        self.schedule_downloads()

    def closeEvent(self, event):
        active = [
            task for task in self.tasks.values()
            if task.get("worker") and task["status"] in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding")
        ]
        if active:
            answer = QMessageBox.question(
                self, "Downloads running",
                "Downloads are still running. Cancel them and exit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            for task in active:
                task["worker"].cancel()
            for task in active:
                task["worker"].wait(3000)
        self.save_preferences()
        self.save_tasks()
        if getattr(self, '_browser_server', None):
            self._browser_server.shutdown()
            self._browser_server.server_close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FDMX()
    window.show()
    sys.exit(app.exec())