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
import subprocess
import datetime
import urllib.request
import urllib.parse
import urllib.error
import socket
import ssl
try:
    import certifi
except ImportError:  # Source runs may use the operating system trust store.
    certifi = None
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.message import Message
from concurrent.futures import ThreadPoolExecutor, as_completed

_MODULE_STARTED_AT = time.perf_counter()

from PySide6.QtCore import QThread, Signal, Qt, QSettings, QSize, QDateTime, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QMenu, QSpinBox,
    QDoubleSpinBox, QHeaderView, QAbstractItemView, QGroupBox, QFrame, QDialog,
    QDateTimeEdit, QCheckBox, QComboBox, QMenuBar, QTabWidget, QTextEdit, QListWidget, QListWidgetItem,
    QSystemTrayIcon, QInputDialog, QProgressDialog, QVBoxLayout as VBoxLayout
)


APP_NAME = "GNS Downloader"
APP_VERSION = "6.41"
CONNECTIONS = 8
MAX_PARTS = 16
CHUNK_SIZE = 64 * 1024
READ_POLL_INTERVAL = 0.2  # seconds; pause responsiveness while waiting for network data


def create_verified_ssl_context():
    """Create a verified TLS context using certifi when it is available."""
    if certifi is not None:
        try:
            bundle = certifi.where()
            if bundle and os.path.isfile(bundle):
                return ssl.create_default_context(cafile=bundle)
        except (OSError, ssl.SSLError):
            pass
    return ssl.create_default_context()


SSL_CONTEXT = create_verified_ssl_context()


def build_url_opener(*handlers):
    """Build an urllib opener that always keeps certificate verification enabled."""
    return urllib.request.build_opener(
        *handlers,
        urllib.request.HTTPSHandler(context=SSL_CONTEXT),
    )


urllib.request.install_opener(build_url_opener())


def open_url(request, timeout=60):
    return urllib.request.urlopen(request, timeout=timeout)

HISTORY_FILE = os.path.join(
    os.path.expanduser("~"), ".fdmx", "history.json"
)
TASKS_FILE = os.path.join(
    os.path.expanduser("~"), ".fdmx", "tasks.json"
)
TASKS_BACKUP_FILE = TASKS_FILE + ".bak"


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
        "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz"},
        "Python": {".py", ".pyw", ".pyi", ".pyc", ".pyo", ".ipynb", ".whl"},
        "Programs": {".exe", ".msi", ".msix", ".apk", ".deb", ".rpm", ".dmg", ".iso", ".appimage", ".app"},
        "Images": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tif", ".tiff", ".ico", ".heic"},
        "Spreadsheets": {".csv", ".tsv", ".ods"},
        "Code": {".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".json", ".xml", ".yaml", ".yml", ".sh", ".bat", ".ps1", ".java", ".kt", ".c", ".cpp", ".h", ".cs", ".go", ".rs"},
    }
    for category, extensions in groups.items():
        if ext in extensions:
            return category
    return "Other"


def create_file_type_icon(category):
    """Create crisp file icons for archive and Python downloads."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    if category == "Compressed":
        # WinRAR-inspired stack of colored archive books and a center strap.
        painter.setBrush(QColor("#2465b4"))
        painter.drawRoundedRect(4, 3, 24, 8, 2, 2)
        painter.setBrush(QColor("#299447"))
        painter.drawRoundedRect(4, 12, 24, 8, 2, 2)
        painter.setBrush(QColor("#b83434"))
        painter.drawRoundedRect(4, 21, 24, 8, 2, 2)
        painter.setBrush(QColor("#e6c77a"))
        painter.drawRoundedRect(14, 3, 5, 26, 1, 1)
        painter.setBrush(QColor("#f3dfaa"))
        painter.drawRoundedRect(13, 13, 7, 5, 1, 1)
        painter.setBrush(QColor("#8b682e"))
        painter.drawRoundedRect(15, 14, 3, 3, 1, 1)
    elif category not in ("Compressed", "Python"):
        colors = {"Video":"#8b5cf6","Audio":"#0ea5e9","Documents":"#2563eb","Programs":"#64748b","Images":"#db2777","Spreadsheets":"#16a34a","Code":"#475569","Other":"#94a3b8"}
        painter.setBrush(QColor(colors.get(category, "#94a3b8")))
        painter.drawRoundedRect(5, 3, 22, 26, 3, 3)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(10, 10, 12, 2)
        painter.drawRect(10, 15, 12, 2)
        painter.drawRect(10, 20, 8, 2)
    elif category == "Python":
        # Python's recognizable blue/yellow interlocking mark.
        painter.setBrush(QColor("#3776ab"))
        painter.drawRoundedRect(4, 3, 19, 14, 5, 5)
        painter.drawRoundedRect(4, 12, 14, 12, 4, 4)
        painter.setBrush(QColor("#ffd343"))
        painter.drawRoundedRect(9, 15, 19, 14, 5, 5)
        painter.drawRoundedRect(14, 8, 14, 12, 4, 4)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(17, 6, 3, 3)
        painter.drawEllipse(12, 23, 3, 3)
    else:
        painter.end()
        return QIcon()
    painter.end()
    return QIcon(pixmap)


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


class RangeNotSupportedError(RuntimeError):
    """Raised when a server rejects or misreports an HTTP byte-range request."""


class DownloadWorker(QThread):
    progress = Signal(int, int, float, float)
    parts_configured = Signal(int)
    completed = Signal(str)
    failed = Signal(str)
    canceled = Signal()
    state = Signal(str)

    def __init__(self, task_id, url, folder, speed_limit_kbps=0, parts_count=CONNECTIONS):
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
        self.destination_path = None
        self.temp_path = None
        self.part_count = CONNECTIONS
        self.configured_part_count = max(1, min(MAX_PARTS, int(parts_count or CONNECTIONS)))

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

    def request_headers(self, start=None, end=None):
        # Use a conventional browser User-Agent: some legacy download hosts
        # reject application-specific clients even though browsers/IDM work.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            # Byte offsets must refer to the representation written to disk.
            "Accept-Encoding": "identity",
        }
        if start is not None:
            headers["Range"] = f"bytes={start}-{end}"
        return headers

    def request(self, start=None, end=None):
        req = urllib.request.Request(
            self.url, headers=self.request_headers(start, end)
        )
        return urllib.request.urlopen(req, timeout=30)

    def probe_download(self):
        """Try a one-byte Range probe, then ordinary GET if the host rejects it."""
        last_error = None
        for use_range in (True, False):
            response = None
            sock = None
            try:
                response = self.request(0, 0) if use_range else self.request()
                sock = self.get_response_socket(response)
                self.register_socket(sock)
                self.wait_if_paused()

                filename = get_filename(response)
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes 0-0/(\d+)", content_range)
                supported = bool(use_range and response.status == 206 and match)
                if match:
                    total = int(match.group(1))
                else:
                    raw_length = response.headers.get("Content-Length", "")
                    total = int(raw_length) if raw_length.isdigit() else 0

                # Consume at most one byte; the response is closed immediately.
                response.read(1)
                return filename, supported, total
            except urllib.error.HTTPError as exc:
                last_error = exc
                try:
                    exc.close()
                except Exception:
                    pass
            except Exception as exc:
                if self.cancel_event.is_set():
                    raise InterruptedError("Download canceled")
                if not self.pause_event.is_set():
                    self.wait_if_paused()
                    continue
                last_error = exc
            finally:
                self.unregister_socket(sock)
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        raise RuntimeError(
            f"Server rejected both Range and ordinary GET requests: {last_error}"
        ) from last_error
        
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
                self.url, headers=self.request_headers(offset, end)
            )
            sock = None
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status != 206:
                        raise RangeNotSupportedError(
                            f"Server returned HTTP {response.status} for a Range request"
                        )
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-{end}/"):
                        raise RangeNotSupportedError(
                            f"Server returned an invalid Content-Range: {content_range!r}"
                        )
                    sock = self.get_response_socket(response)
                    self.register_socket(sock)
                    mode = "ab" if received else "wb"
                    with open(path, mode) as output:
                        last_sync = time.monotonic()
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
                            # Make partial data durable without forcing a disk sync per chunk.
                            if time.monotonic() - last_sync >= 1.0:
                                os.fsync(output.fileno())
                                last_sync = time.monotonic()
                        output.flush()
                        os.fsync(output.fileno())
                failures = 0
            except InterruptedError:
                raise
            except RangeNotSupportedError:
                raise
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 403, 405, 416, 501):
                    status = exc.code
                    exc.close()
                    raise RangeNotSupportedError(
                        f"Server rejected HTTP Range with status {status}"
                    ) from exc
                if self.cancel_event.is_set():
                    raise InterruptedError("Download canceled")
                if not self.pause_event.is_set():
                    self.wait_if_paused()
                    continue
                failures += 1
                if failures > 3:
                    raise
                time.sleep(min(1.0 * failures, 3.0))
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
        temp_path = destination + f".{self.task_id}.fdmx.tmp"
        self.temp_path = temp_path
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

    def _write_parts_manifest(self, temp_folder, total, count):
        manifest_path = os.path.join(temp_folder, "parts.json")
        temp_path = manifest_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump({
                "total": int(total), "count": int(count),
                "version": 1
            }, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, manifest_path)

    def download_multi(self, destination, total):
        self.reset_progress(total)
        with PersistentTempDirectory(os.path.join(self.folder, f".fdmx_{self.task_id}.parts")) as temp_folder:
            manifest_path = os.path.join(temp_folder, "parts.json")
            manifest = None
            try:
                with open(manifest_path, "r", encoding="utf-8") as file:
                    candidate = json.load(file)
                candidate_count = int(candidate.get("count", 0))
                if int(candidate.get("total", 0)) == total and 1 <= candidate_count <= min(MAX_PARTS, total):
                    manifest = candidate
            except (OSError, ValueError, TypeError, AttributeError):
                manifest = None

            # If a manifest exists but is invalid or belongs to a different file size,
            # discard its fragments instead of guessing their byte-range layout.
            if os.path.exists(manifest_path) and manifest is None:
                for filename in os.listdir(temp_folder):
                    if filename.startswith("part_") and filename.endswith(".tmp"):
                        try:
                            os.remove(os.path.join(temp_folder, filename))
                        except OSError:
                            pass
                try:
                    os.remove(manifest_path)
                except OSError:
                    pass

            existing_parts = any(
                os.path.isfile(os.path.join(temp_folder, f"part_{index:02d}.tmp"))
                for index in range(MAX_PARTS)
            )
            if manifest:
                # Keep the original partition map so resume never mixes byte ranges.
                parts_count = int(manifest["count"])
            elif existing_parts:
                # Legacy fixed-eight fragments must keep their original byte-range map.
                parts_count = min(CONNECTIONS, total)
                self._write_parts_manifest(temp_folder, total, parts_count)
            else:
                # New downloads always use the configured fixed connection count.
                parts_count = min(self.configured_part_count, total)
                self._write_parts_manifest(temp_folder, total, parts_count)

            self.part_count = parts_count
            self.parts_configured.emit(parts_count)
            ranges = []
            for index in range(parts_count):
                start = (total * index) // parts_count
                end = (total * (index + 1)) // parts_count - 1
                ranges.append((index, start, end))

            existing_bytes = 0
            for index, start, end in ranges:
                part_path = os.path.join(temp_folder, f"part_{index:02d}.tmp")
                expected = end - start + 1
                if not os.path.isfile(part_path):
                    continue
                try:
                    received = os.path.getsize(part_path)
                    if received > expected:
                        os.remove(part_path)
                        received = 0
                    existing_bytes += received
                except OSError:
                    continue
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
            filename, supported, total = self.probe_download()
            self.wait_if_paused()

            os.makedirs(self.folder, exist_ok=True)
            destination = unique_path(self.folder, filename)
            self.destination_path = destination

            last_error = None
            for attempt in range(3):
                if self.cancel_event.is_set():
                    raise InterruptedError("Download canceled")
                try:
                    if supported and total > 1:
                        try:
                            self.download_multi(destination, total)
                        except RangeNotSupportedError:
                            # The initial probe can succeed while later byte ranges
                            # are blocked by a CDN/proxy. Fall back to a clean stream.
                            self.state.emit("Range unavailable; using single connection")
                            parts_dir = os.path.join(
                                self.folder, f".fdmx_{self.task_id}.parts"
                            )
                            shutil.rmtree(parts_dir, ignore_errors=True)
                            self.download_single(destination)
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
            parts_dir = os.path.join(self.folder, f".fdmx_{self.task_id}.parts")
            if os.path.isdir(parts_dir):
                shutil.rmtree(parts_dir, ignore_errors=True)
            for partial in (self.temp_path, destination + ".fdmx.tmp" if destination else None):
                if partial and os.path.isfile(partial):
                    try:
                        os.remove(partial)
                    except OSError:
                        pass
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


class FileInfoWorker(QThread):
    info_ready = Signal(dict)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cancel_event = threading.Event()
        self._response_lock = threading.Lock()
        self._active_response = None

    def cancel(self):
        self.cancel_event.set()
        with self._response_lock:
            response = self._active_response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def run(self):
        info = {"size": -1, "name": "", "content_type": "", "accept_ranges": False, "error": ""}
        headers = {"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "*/*"}
        response = None
        try:
            request = urllib.request.Request(self.url, headers=headers, method="HEAD")
            try:
                response = urllib.request.urlopen(request, timeout=4)
            except Exception:
                if self.cancel_event.is_set():
                    return
                request = urllib.request.Request(self.url, headers={**headers, "Range": "bytes=0-0"})
                response = urllib.request.urlopen(request, timeout=4)
            with self._response_lock:
                self._active_response = response
            if self.cancel_event.is_set():
                return
            content_range = response.headers.get("Content-Range", "")
            if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit():
                info["size"] = int(content_range.rsplit("/", 1)[1])
            else:
                raw_size = response.headers.get("Content-Length", "")
                if raw_size.isdigit():
                    info["size"] = int(raw_size)
            info["content_type"] = response.headers.get("Content-Type", "")
            info["accept_ranges"] = "bytes" in response.headers.get("Accept-Ranges", "").lower() or response.status == 206
            disposition = response.headers.get("Content-Disposition", "")
            if disposition:
                message = Message()
                message["content-disposition"] = disposition
                filename = message.get_filename()
                if filename:
                    info["name"] = os.path.basename(filename)
        except Exception as exc:
            info["error"] = str(exc)
        finally:
            if response is not None:
                try: response.close()
                except Exception: pass
            with self._response_lock:
                self._active_response = None
        if not self.cancel_event.is_set():
            self.info_ready.emit(info)


class DownloadDetailsDialog(QDialog):
    """Live per-download window showing metadata, progress and byte segments."""
    def __init__(self, parent, task, connections=CONNECTIONS):
        super().__init__(parent)
        self.task = task
        self.parent_window = parent
        self.connections = connections
        self.setWindowTitle("Download details — " + task.get("name", "Download"))
        self.resize(820, 540)
        self.setMinimumSize(680, 420)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        layout = QVBoxLayout(self)
        self.title_label = QLabel(task.get("name", "Download"))
        self.title_label.setStyleSheet("font-size:16pt;font-weight:700;padding:4px;")
        layout.addWidget(self.title_label)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.url_label = QLabel()
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_label.setWordWrap(True)
        layout.addWidget(self.url_label)

        self.folder_label = QLabel()
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(22)
        layout.addWidget(self.progress_bar)

        actions = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.resume_btn = QPushButton("Resume")
        self.cancel_btn = QPushButton("Cancel")
        self.retry_btn = QPushButton("Retry")
        self.start_btn = QPushButton("Start")
        self.open_btn = QPushButton("Open")
        self.close_btn = QPushButton("Close")
        self.start_btn.clicked.connect(self.start_download)
        self.pause_btn.clicked.connect(self.pause_download)
        self.resume_btn.clicked.connect(self.resume_download)
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.retry_btn.clicked.connect(self.retry_download)
        self.open_btn.clicked.connect(self.open_downloaded_file)
        self.close_btn.clicked.connect(self.close)
        for button in (self.start_btn, self.pause_btn, self.resume_btn, self.cancel_btn, self.retry_btn, self.open_btn, self.close_btn):
            button.setMinimumHeight(36)
            actions.addWidget(button)
        self.open_btn.setVisible(False)
        layout.addLayout(actions)

        # Each download owns its own post-completion action.
        post_action_row = QHBoxLayout()
        self.post_action_enabled = QCheckBox("After this download finishes:")
        self.post_action_enabled.setChecked(bool(task.get("post_action_enabled", False)))
        self.post_action = QComboBox()
        self.post_action.addItem("Do nothing", "none")
        self.post_action.addItem("Shut down Windows", "shutdown")
        self.post_action.addItem("Log out of Windows", "logout")
        self.post_action.addItem("Hibernate Windows", "hibernate")
        saved_action = task.get("post_action", "none")
        self.post_action.setCurrentIndex(max(0, self.post_action.findData(saved_action)))
        self.post_action.setEnabled(self.post_action_enabled.isChecked())
        self.post_action_enabled.toggled.connect(self.post_action.setEnabled)
        self.post_action_enabled.toggled.connect(self.save_post_action_settings)
        self.post_action.currentIndexChanged.connect(self.save_post_action_settings)
        self.post_action_enabled.setToolTip("Choose an action that runs only after this specific download completes.")
        self.post_action.setToolTip("The selected action is saved with this download.")
        post_action_row.addWidget(self.post_action_enabled)
        post_action_row.addWidget(self.post_action, 1)
        layout.addLayout(post_action_row)

        parts_title = QLabel("DOWNLOAD PARTS / SEGMENTS")
        parts_title.setStyleSheet("font-size:12pt;font-weight:700;padding-top:8px;")
        layout.addWidget(parts_title)

        self.parts_table = QTableWidget(0, 5)
        self.parts_table.setHorizontalHeaderLabels(["Part", "Byte range", "Downloaded", "Expected", "State"])
        self.parts_table.setAlternatingRowColors(True)
        self.parts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.parts_table.verticalHeader().setVisible(False)
        self.parts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col in (0, 2, 3, 4):
            self.parts_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self.parts_table, 1)

        # Reuse the main window's palette and stylesheet instead of imposing a separate dark theme.
        if parent is not None:
            self.setPalette(parent.palette())
            self.setStyleSheet(parent.styleSheet())
        self.setAutoFillBackground(True)

        self.refresh_data()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(700)

    def save_post_action_settings(self, *_):
        self.task["post_action_enabled"] = self.post_action_enabled.isChecked()
        self.task["post_action"] = self.post_action.currentData() or "none"
        if not self.task["post_action_enabled"]:
            self.task["post_action_done"] = False
        self.parent_window.save_tasks()

    def open_downloaded_file(self):
        path = self.task.get("path", "")
        if self.task.get("status") != "Completed" or not path or not os.path.isfile(path):
            QMessageBox.warning(self, "File unavailable", "The completed file could not be found.")
            self.refresh_data()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path))):
            QMessageBox.warning(self, "Open failed", "Windows could not open this file.")

    def start_download(self):
        if self.task.get("status") != "Ready":
            return
        self.task["status"] = "Queued"
        self.task["scheduled_at"] = ""
        self.parent_window.save_tasks()
        self.parent_window.refresh_table()
        self.parent_window.start_queue()
        self.refresh_data()

    def pause_download(self):
        task = self.task
        worker = task.get("worker")
        if worker and task.get("status") in ("Downloading", "Checking server", "Retrying", "Checking metadata", "Seeding"):
            worker.pause()
            task["status"] = "Paused"
            self.parent_window.refresh_table()
            self.refresh_data()

    def resume_download(self):
        task = self.task
        worker = task.get("worker")
        if worker and task.get("status") == "Paused":
            worker.resume()
            task["status"] = "Downloading"
            self.parent_window.refresh_table()
            self.refresh_data()

    def cancel_download(self):
        task = self.task
        self.parent_window.cancel_task(task.get("id"))
        self.refresh_data()

    def retry_download(self):
        task = self.task
        if task.get("status") not in ("Failed", "Canceled"):
            return
        task.update({
            "status": "Queued", "downloaded": 0, "total": 0, "retry_attempts": 0,
            "speed": 0.0, "eta": -1.0, "path": "", "worker": None
        })
        self.parent_window.schedule_downloads()
        self.parent_window.refresh_table()
        self.refresh_data()

    def refresh_data(self):
        task = self.task
        name = task.get("name", "Download")
        status = task.get("status", "Unknown")
        active_states = ("Downloading", "Checking server", "Retrying", "Seeding")
        completed = status == "Completed"
        for button in (self.start_btn, self.pause_btn, self.resume_btn, self.cancel_btn, self.retry_btn):
            button.setVisible(not completed)
        self.open_btn.setVisible(completed)
        self.close_btn.setVisible(True)
        self.post_action_enabled.setEnabled(not completed)
        self.post_action.setEnabled(not completed and self.post_action_enabled.isChecked())
        self.start_btn.setVisible(not completed and status in ("Ready", "Checking metadata"))
        self.start_btn.setEnabled(status == "Ready")
        self.pause_btn.setEnabled(status in ("Downloading", "Checking server", "Seeding"))
        self.resume_btn.setEnabled(status == "Paused")
        self.cancel_btn.setEnabled(status in active_states or status in ("Checking metadata", "Paused", "Queued", "Ready"))
        self.retry_btn.setEnabled(status in ("Failed", "Canceled"))
        final_path_for_open = task.get("path", "")
        self.open_btn.setEnabled(completed and bool(final_path_for_open) and os.path.isfile(final_path_for_open))
        downloaded = int(task.get("downloaded") or 0)
        total = int(task.get("total") or 0)
        speed = float(task.get("speed") or 0)
        eta = task.get("eta", -1)
        percent = min(100, int(downloaded * 100 / total)) if total else (100 if status == "Completed" else 0)
        size_text = f"{format_bytes(downloaded)} / {format_bytes(total)}" if total else format_bytes(downloaded)
        speed_text = format_bytes(speed) + "/s"
        eta_text = format_duration(eta)
        self.setWindowTitle("Download details — " + name)
        self.title_label.setText(name)
        metadata_size = format_bytes(total) if total > 0 else "Unknown"
        content_type = task.get("content_type", "Unknown") or "Unknown"
        self.summary_label.setText(
            f"Status: {status}    |    File size: {metadata_size}\n"
            f"Progress: {percent}%    |    Downloaded: {size_text}\n"
            f"Type: {content_type}    |    Speed: {speed_text}    |    ETA: {eta_text}"
        )
        self.url_label.setText("URL: " + str(task.get("url", "")))
        self.folder_label.setText("Save folder: " + str(task.get("folder", "")))
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}%  —  {size_text}")
        if completed:
            self.summary_label.setText(self.summary_label.text() + "\nDownload finished — Open the file or Close this window.")
        elif task.get("kind") != "torrent":
            selected_parts = int(task.get("parts_count") or 0)
            if selected_parts:
                self.summary_label.setText(
                    self.summary_label.text()
                    + f"\nFixed connection mode: {selected_parts} part(s) from user settings"
                )
            elif status in ("Downloading", "Checking server", "Retrying"):
                self.summary_label.setText(self.summary_label.text() + "\nFixed connection mode: waiting to start configured parts…")

        if task.get("kind") == "torrent":
            self.parts_table.setRowCount(1)
            values = ["Torrent", "Managed by torrent engine", size_text, "—", status]
            for col, value in enumerate(values):
                self.parts_table.setItem(0, col, QTableWidgetItem(value))
            return

        final_path = task.get("path", "")
        completed = status == "Completed" and final_path and os.path.isfile(final_path)
        if completed:
            total = os.path.getsize(final_path)
        if total <= 0:
            self.parts_table.setRowCount(1)
            self.parts_table.setItem(0, 0, QTableWidgetItem("Waiting"))
            self.parts_table.setItem(0, 1, QTableWidgetItem("Part details appear after server check"))
            for col in (2, 3, 4):
                self.parts_table.setItem(0, col, QTableWidgetItem("—"))
            return

        count = min(int(task.get("parts_count") or self.connections), total)
        parts_dir = os.path.join(task.get("folder", ""), ".fdmx_" + task.get("id", "") + ".parts")
        self.parts_table.setRowCount(count)
        for index in range(count):
            start = (total * index) // count
            end = (total * (index + 1)) // count - 1
            expected = end - start + 1
            part_path = os.path.join(parts_dir, "part_%02d.tmp" % index)
            received = expected if completed else (
                min(os.path.getsize(part_path), expected) if os.path.isfile(part_path) else 0
            )
            state = "Completed" if received >= expected else ("Downloading" if received else "Waiting")
            values = [
                f"#{index + 1}", f"{format_bytes(start)} – {format_bytes(end)}",
                format_bytes(received), format_bytes(expected), state
            ]
            for col, value in enumerate(values):
                self.parts_table.setItem(index, col, QTableWidgetItem(value))



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




class WebsitePageParser(HTMLParser):
    """Collect navigational links and downloadable resources from an HTML page."""
    RESOURCE_ATTRS = ("src", "href", "poster", "data-src", "data-href", "content")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        srcset = values.get("srcset", "")
        if srcset:
            for candidate in srcset.split(","):
                candidate_url = candidate.strip().split(" ")[0]
                if candidate_url:
                    self.links.add(candidate_url)
        for attr in self.RESOURCE_ATTRS:
            value = values.get(attr)
            if value:
                value = value.strip()
                if value and not value.startswith(("#", "data:", "javascript:", "mailto:", "tel:")):
                    self.links.add(value)
        if tag.lower() == "meta":
            content = values.get("content", "")
            if content and re.match(r"(?i)^https?://", content.strip()):
                self.links.add(content.strip())


class WebsiteScanWorker(QThread):
    found = Signal(str, str, str, int)
    progress = Signal(str)
    finished_scan = Signal(int)
    failed_scan = Signal(str)

    def __init__(self, start_url, include_external=False, max_pages=500, max_depth=4):
        super().__init__()
        self.start_url = self.prepare_url(start_url)
        self.include_external = include_external
        self.max_pages = max_pages
        self.max_depth = max_depth
        self._stop = threading.Event()
        self._skip_current = threading.Event()
        self.current_page = ""
        self.seen_pages = set()
        self.seen_resources = set()
        self._resource_lock = threading.Lock()
        self._size_executor = ThreadPoolExecutor(max_workers=16)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8"
        }

    @staticmethod
    def prepare_url(url):
        url = (url or "").strip()
        if not re.match(r"(?i)^https?://", url):
            url = "https://" + url.lstrip("/")
        return WebsiteScanWorker.normalize_url(url)

    @staticmethod
    def normalize_url(url):
        try:
            parsed = urllib.parse.urlsplit(url.strip())
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                return ""
            return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                                            parsed.path or "/", parsed.query, ""))
        except Exception:
            return ""

    def stop(self):
        self._stop.set()

    def skip_current_page(self):
        self._skip_current.set()

    @staticmethod
    def _same_site(host_a, host_b):
        a = (host_a or "").lower().removeprefix("www.")
        b = (host_b or "").lower().removeprefix("www.")
        return a == b

    def _open(self, url, method="GET", read_limit=0):
        request = urllib.request.Request(url, headers=self.headers, method=method)
        response = urllib.request.urlopen(request, timeout=18)
        if read_limit:
            data = response.read(read_limit)
        else:
            data = b""
        return response, data

    def _fetch_page(self, url):
        candidates = [url]
        parsed = urllib.parse.urlsplit(url)
        alternate = ("http" if parsed.scheme == "https" else "https")
        candidates.append(urllib.parse.urlunsplit((alternate, parsed.netloc, parsed.path, parsed.query, "")))
        last_error = None
        for candidate in candidates:
            try:
                response, data = self._open(candidate, "GET", 4 * 1024 * 1024)
                final_url = self.normalize_url(response.geturl())
                content_type = response.headers.get("Content-Type", "").lower()
                charset = response.headers.get_content_charset() or "utf-8"
                response.close()
                return final_url, content_type, data, charset
            except Exception as exc:
                last_error = exc
        raise last_error or OSError("Unable to open URL")

    def _probe_link(self, url):
        """Use response headers to distinguish extensionless files from HTML pages."""
        parsed = urllib.parse.urlsplit(url)
        candidates = [url, urllib.parse.urlunsplit((
            "http" if parsed.scheme == "https" else "https",
            parsed.netloc, parsed.path, parsed.query, ""
        ))]
        for candidate in candidates:
            for method in ("HEAD", "GET"):
                try:
                    response, data = self._open(candidate, method, 2048 if method == "GET" else 0)
                    final_url = self.normalize_url(response.geturl())
                    content_type = response.headers.get("Content-Type", "").lower()
                    response.close()
                    return final_url or candidate, content_type
                except Exception:
                    continue
        return url, ""

    def run(self):
        try:
            if not self.start_url:
                raise ValueError("Enter a valid website address.")
            base_host = (urllib.parse.urlsplit(self.start_url).hostname or "").lower()
            queue = [(self.start_url, 0)]
            while queue and len(self.seen_pages) < self.max_pages and not self._stop.is_set():
                page_url, depth = queue.pop(0)
                page_url = self.normalize_url(page_url)
                if not page_url or page_url in self.seen_pages:
                    continue
                host = (urllib.parse.urlsplit(page_url).hostname or "").lower()
                if not self.include_external and not self._same_site(host, base_host):
                    continue
                self.seen_pages.add(page_url)
                self.current_page = page_url
                self._skip_current.clear()
                self.progress.emit(f"Scanning {len(self.seen_pages)}/{self.max_pages}: {page_url}")
                try:
                    final_url, content_type, raw, charset = self._fetch_page(page_url)
                except Exception as exc:
                    self.progress.emit(f"Skipped inaccessible page: {page_url} ({exc})")
                    continue
                if self._skip_current.is_set():
                    self.progress.emit(f"Skipped current page: {page_url}")
                    continue
                if not final_url:
                    continue
                if "html" not in content_type and "xhtml" not in content_type:
                    self._add_resource(final_url, content_type)
                    continue
                try:
                    html = raw.decode(charset, errors="replace")
                except LookupError:
                    html = raw.decode("utf-8", errors="replace")
                parser = WebsitePageParser()
                parser.feed(html)
                links = set(parser.links)
                # Ignore very basic/static subpages; keep the start page and pages
                # with several signs of real application/content complexity.
                if depth > 0:
                    lower_html = html.lower()
                    complexity = sum((
                        len(links) >= 8,
                        len(re.findall(r"<form\b", lower_html)) >= 1,
                        len(re.findall(r"<script\b", lower_html)) >= 2,
                        any(token in lower_html for token in ("<nav", "application/json", "__next_data__", "wp-content", "data-reactroot", "ng-version")),
                        len(html) >= 18000,
                        len(re.findall(r"<(?:article|section|main)\b", lower_html)) >= 2
                    ))
                    if complexity < 2:
                        self.progress.emit(f"Skipped simple page: {page_url}")
                        continue
                # Discover resources referenced from inline CSS and stylesheets.
                for match in re.findall(r"""url\(['"]?(.*?)['"]?\)""", html, flags=re.I):
                    if match and not match.strip().startswith("data:"):
                        links.add(match.strip())
                probe_urls = []
                for raw_link in links:
                    if self._stop.is_set():
                        break
                    absolute = self.normalize_url(urllib.parse.urljoin(final_url, raw_link))
                    if not absolute:
                        continue
                    parsed = urllib.parse.urlsplit(absolute)
                    link_host = (parsed.hostname or "").lower()
                    if not self.include_external and not self._same_site(link_host, base_host):
                        continue
                    path = urllib.parse.unquote(parsed.path).lower()
                    ext = os.path.splitext(path)[1]
                    if ext:
                        self._add_resource(absolute, mimetypes.guess_type(path)[0] or "")
                        if ext == ".css":
                            self._scan_css(absolute)
                    else:
                        probe_urls.append(absolute)
                with ThreadPoolExecutor(max_workers=16) as probe_pool:
                    futures = {probe_pool.submit(self._probe_link, link): link for link in probe_urls}
                    for future in as_completed(futures):
                        if self._stop.is_set():
                            break
                        original = futures[future]
                        try:
                            checked_url, checked_type = future.result()
                        except Exception:
                            checked_url, checked_type = original, ""
                        if "html" in checked_type or "xhtml" in checked_type or not checked_type:
                            if depth < self.max_depth and checked_url not in self.seen_pages:
                                queue.append((checked_url, depth + 1))
                        else:
                            self._add_resource(checked_url, checked_type)
            self._size_executor.shutdown(wait=True)
            self.finished_scan.emit(len(self.seen_resources))
        except Exception as exc:
            try: self._size_executor.shutdown(wait=False, cancel_futures=True)
            except Exception: pass
            self.failed_scan.emit(str(exc))

    def _scan_css(self, css_url):
        try:
            response, raw = self._open(css_url, "GET", 2 * 1024 * 1024)
            base = response.geturl()
            response.close()
            text = raw.decode("utf-8", errors="replace")
            for match in re.findall(r"""url\(['"]?(.*?)['"]?\)""", text, flags=re.I):
                value = match.strip().strip(" '\"")
                if value and not value.startswith("data:"):
                    target = self.normalize_url(urllib.parse.urljoin(base, value))
                    if target:
                        self._add_resource(target, mimetypes.guess_type(target)[0] or "")
        except Exception:
            pass

    def _add_resource(self, url, content_type):
        with self._resource_lock:
            if url in self.seen_resources:
                return
            self.seen_resources.add(url)
        parsed = urllib.parse.urlsplit(url)
        name = os.path.basename(urllib.parse.unquote(parsed.path)) or "index"
        if not os.path.splitext(name)[1]:
            guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
            if guessed:
                name += guessed
        self._size_executor.submit(self._emit_resource_info, url, name, content_type)

    def _emit_resource_info(self, url, name, content_type):
        size = -1
        try:
            request = urllib.request.Request(url, headers=self.headers, method="HEAD")
            with urllib.request.urlopen(request, timeout=7) as response:
                raw_size = response.headers.get("Content-Length")
                if raw_size and raw_size.isdigit():
                    size = int(raw_size)
        except Exception:
            pass
        self.found.emit(url, name, content_type or mimetypes.guess_type(name)[0] or "Unknown", size)


class AdminLoginFinderWorker(QThread):
    """Low-impact discovery of public login routes and exposed server metadata."""
    result_ready = Signal(dict)
    progress = Signal(str)
    LOGIN_PATHS = (
        "/login", "/login/", "/signin", "/sign-in", "/auth/login",
        "/account/login", "/admin", "/admin/", "/admin/login",
        "/administrator", "/administrator/", "/admin.php", "/dashboard",
        "/user/login", "/wp-login.php", "/wp-admin/", "/joomla/administrator/",
        "/phpmyadmin/", "/pma/", "/manager/html", "/cpanel", "/webmail", "/backend/"
    )

    def __init__(self, start_url, find_admin=True, profile=True, collect_domain=True):
        super().__init__()
        self.start_url = WebsiteScanWorker.prepare_url(start_url)
        self.find_admin = find_admin
        self.profile = profile
        self.collect_domain = collect_domain
        self._stop_requested = threading.Event()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"
        }

    def stop(self):
        self._stop_requested.set()

    def _request(self, url, method="GET", limit=262144):
        if self._stop_requested.is_set():
            raise InterruptedError("Discovery stopped by user.")
        request = urllib.request.Request(url, headers=self.headers, method=method)
        try:
            response = urllib.request.urlopen(request, timeout=9)
        except urllib.error.HTTPError as error:
            response = error
        body = response.read(limit) if method == "GET" else b""
        result = {"status": getattr(response, "status", response.getcode()),
                  "url": response.geturl(), "headers": dict(response.headers.items()), "body": body}
        response.close()
        return result

    @staticmethod
    def _server_family(server):
        value = (server or "").lower()
        for token, name in (("nginx", "Nginx"), ("apache", "Apache HTTP Server"),
                            ("microsoft-iis", "Microsoft IIS"), ("iis", "Microsoft IIS"),
                            ("openresty", "OpenResty"), ("caddy", "Caddy"),
                            ("lighttpd", "Lighttpd"), ("litespeed", "LiteSpeed"),
                            ("cloudflare", "Cloudflare proxy")):
            if token in value:
                return name
        return "Not disclosed / unidentified"

    @staticmethod
    def _detect_stack(html, headers):
        text = (html or "").lower()
        header_text = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
        checks = (
            ("WordPress", ("wp-content/", "wp-includes/", "wp-json")),
            ("Drupal", ("drupal.settings", "/sites/default/")),
            ("Joomla", ("content=\"joomla!", "/media/system/js/")),
            ("Magento", ("mage/cookies", "magento_")),
            ("Shopify", ("cdn.shopify.com", "shopify.theme")),
            ("Laravel", ("laravel_session", "csrf-token")),
            ("Django", ("csrftoken", "django")),
            ("ASP.NET", ("asp.net", "__viewstate", "asp.net_sessionid")),
            ("Next.js", ("__next_data__", "/_next/static/")),
            ("React", ("react-dom", "data-reactroot")),
            ("Vue.js", ("vue.js", "__vue__")),
            ("Angular", ("ng-version", "angular"))
        )
        found = [name for name, markers in checks if any(m in text or m in header_text for m in markers)]
        generator = re.search(r"""<meta[^>]+name=["']generator["'][^>]+content=["']([^"']+)""", html or "", re.I)
        return found, generator.group(1) if generator else ""

    def _advanced_profile(self, home, parsed):
        """Collect bounded, read-only, same-origin technology and security evidence."""
        origin = f"{parsed.scheme}://{parsed.netloc}"
        host = parsed.hostname or ""
        evidence = []
        responses = []
        html = home.get("body", b"").decode("utf-8", errors="replace")
        headers = home.get("headers", {})

        def add(family, technology, source, detail, weight=20):
            evidence.append({
                "family": family, "technology": technology, "source": source,
                "detail": str(detail)[:260], "weight": int(weight)
            })

        def fetch(path, label):
            if self._stop_requested.is_set():
                return None
            url = urllib.parse.urljoin(origin + "/", path.lstrip("/"))
            try:
                result = self._request(url, "GET", 160 * 1024)
                responses.append({
                    "path": path, "status": int(result["status"]),
                    "final_url": result["url"], "headers": result["headers"]
                })
                return result
            except Exception as exc:
                responses.append({"path": path, "status": None, "error": type(exc).__name__})
                return None

        # Homepage is one evidence source; a few conventional public resources
        # provide independent signals without crawling or authentication bypass.
        responses.append({
            "path": "/", "status": int(home.get("status", 0)),
            "final_url": home.get("url", self.start_url), "headers": headers
        })
        header_text = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
        html_lower = html.lower()

        server = headers.get("Server", "")
        powered = headers.get("X-Powered-By", "")
        for token, name in (
            ("nginx", "Nginx"), ("apache", "Apache HTTP Server"),
            ("microsoft-iis", "Microsoft IIS"), ("openresty", "OpenResty"),
            ("litespeed", "LiteSpeed"), ("caddy", "Caddy"), ("cloudflare", "Cloudflare")
        ):
            if token in server.lower():
                add("Web Server", name, "HTTP Server header", server, 35)
        if "asp.net" in powered.lower() or "asp.net" in header_text:
            add("Framework", "ASP.NET", "HTTP response headers", powered or header_text, 30)

        # Framework/CMS markers from HTML, cookies, JS globals and resource paths.
        marker_sets = (
            ("WordPress", (("wp-content/", 25), ("wp-includes/", 25), ("wp-json", 20))),
            ("Drupal", (("drupal.settings", 30), ("/sites/default/", 20), ("drupal.js", 20))),
            ("Joomla", (("content=\"joomla", 30), ("/media/system/js/", 20))),
            ("Magento", (("mage/cookies", 25), ("magento_", 25), ("mage-cache", 20))),
            ("Shopify", (("cdn.shopify.com", 30), ("shopify.theme", 25))),
            ("Laravel", (("laravel_session", 35), ("name=\"csrf-token\"", 15))),
            ("Django", (("csrftoken", 30), ("django", 15))),
            ("ASP.NET", (("__viewstate", 40), ("__eventvalidation", 35),
                         ("asp.net_sessionid", 35), (".aspx", 20))),
            ("Next.js", (("__next_data__", 35), ("/_next/static/", 30))),
            ("React", (("react-dom", 25), ("data-reactroot", 25), ("__react", 15))),
            ("Vue.js", (("vue.js", 25), ("__vue__", 25), ("data-v-", 15))),
            ("Angular", (("ng-version=", 35), ("ng-app", 20), ("angular", 15)))
        )
        cookie_text = " ".join(v for k, v in headers.items() if k.lower() == "set-cookie").lower()
        for tech, markers in marker_sets:
            for marker_text, weight in markers:
                haystack = html_lower + "\n" + cookie_text + "\n" + header_text
                if marker_text in haystack:
                    source = "HTML" if marker_text in html_lower else ("Cookie name" if marker_text in cookie_text else "HTTP header")
                    add("Framework / CMS", tech, source, f"Matched marker: {marker_text}", weight)
                    break

        # CDN and proxy clues. These identify an observed edge, not necessarily
        # the origin server behind it.
        cdn_checks = (
            ("Cloudflare", ("cf-ray", "cf-cache-status", "cloudflare")),
            ("Akamai", ("akamai", "x-akamai", "akamaized.net")),
            ("Fastly", ("x-served-by", "x-cache-hits", "fastly")),
            ("Amazon CloudFront", ("x-amz-cf-id", "x-amz-cf-pop", "cloudfront"))
        )
        for name, tokens in cdn_checks:
            matched = [t for t in tokens if t in header_text or t in html_lower]
            if matched:
                add("CDN / Proxy", name, "HTTP headers / HTML", "Matched: " + ", ".join(matched), 30)
        if any(x in header_text for x in ("via:", "x-cache:", "x-proxy-", "forwarded:")):
            add("CDN / Proxy", "Reverse proxy / intermediary", "HTTP response headers",
                "Proxy/cache forwarding header observed", 18)

        # Fetch only a small fixed set of public metadata endpoints.
        for path in ("/robots.txt", "/.well-known/security.txt"):
            item = fetch(path, path)
            if item:
                body = item.get("body", b"").decode("utf-8", errors="replace").lower()
                if path == "/robots.txt" and "sitemap:" in body:
                    add("Site metadata", "Sitemap declaration", "robots.txt", "Sitemap directive found", 10)

        # Inspect a few same-origin script/style URLs referenced by the homepage.
        asset_paths = []
        for match in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+\.(?:js|css)(?:\?[^"']*)?)["']""", html, re.I):
            absolute = urllib.parse.urljoin(self.start_url, match.group(1))
            parsed_asset = urllib.parse.urlsplit(absolute)
            if (parsed_asset.hostname or "").lower() == host.lower() and absolute not in asset_paths:
                asset_paths.append(absolute)
            if len(asset_paths) >= 3:
                break
        for asset_url in asset_paths:
            if self._stop_requested.is_set():
                break
            try:
                asset = self._request(asset_url, "GET", 96 * 1024)
                asset_text = asset.get("body", b"").decode("utf-8", errors="ignore").lower()
                asset_name = urllib.parse.urlsplit(asset_url).path.rsplit("/", 1)[-1]
                for token, tech in (("wp-content", "WordPress"), ("jquery", "jQuery"),
                                    ("react", "React"), ("vue", "Vue.js"),
                                    ("angular", "Angular"), ("next", "Next.js")):
                    if token in asset_text or token in asset_name.lower():
                        add("Framework / CMS", tech, "JavaScript/CSS asset",
                            f"Marker found in same-origin asset: {asset_name}", 20)
                responses.append({"path": urllib.parse.urlsplit(asset_url).path,
                                  "status": int(asset["status"]), "final_url": asset["url"],
                                  "headers": asset["headers"]})
            except Exception:
                pass

        # TLS certificate metadata is read from a normal verified TLS handshake.
        tls = {"status": "not_assessed"}
        if parsed.scheme.lower() == "https":
            try:
                context = ssl.create_default_context()
                with socket.create_connection((host, parsed.port or 443), timeout=6) as raw:
                    with context.wrap_socket(raw, server_hostname=host) as secured:
                        cert = secured.getpeercert()
                        subject = dict(x[0] for x in cert.get("subject", []))
                        issuer = dict(x[0] for x in cert.get("issuer", []))
                        tls = {
                            "status": "observed",
                            "tls_version": secured.version() or "Unknown",
                            "cipher": (secured.cipher() or ["Unknown"])[0],
                            "subject": subject.get("commonName", host),
                            "issuer": issuer.get("commonName", "Unknown"),
                            "not_after": cert.get("notAfter", "Unknown")
                        }
            except Exception as exc:
                tls = {"status": "unavailable", "reason": type(exc).__name__}

        # Score by distinct source types to avoid treating repeated copies of
        # the same header as independent confirmation.
        grouped = {}
        for item in evidence:
            key = (item["family"], item["technology"])
            grouped.setdefault(key, []).append(item)
        detections = []
        for (family, technology), items in sorted(grouped.items()):
            score = min(100, sum(x["weight"] for x in items))
            independent = len({x["source"] for x in items})
            confidence = "High" if score >= 65 and independent >= 2 else (
                "Medium" if score >= 35 else "Low")
            detections.append({
                "family": family, "technology": technology, "score": score,
                "confidence": confidence, "evidence_count": len(items), "evidence": items
            })

        # Operating system remains a cautious inference. Edge headers can describe
        # a CDN rather than the origin host, so the result is never asserted as fact.
        os_hints = []
        os_text = (header_text + " " + html_lower)
        for token, label in (("windows", "Windows"), ("win32", "Windows"),
                             ("ubuntu", "Ubuntu/Linux"), ("debian", "Debian/Linux"),
                             ("centos", "RHEL-family Linux"), ("red hat", "RHEL-family Linux"),
                             ("linux", "Linux")):
            if token in os_text and label not in os_hints:
                os_hints.append(label)
        os_result = {
            "value": os_hints[0] if len(os_hints) == 1 else "Unknown / ambiguous",
            "confidence": "Low" if os_hints else "Not assessable",
            "note": "Indirect fingerprint only; CDN/proxy headers may describe the edge, not the origin."
        }

        security_names = (
            "Strict-Transport-Security", "Content-Security-Policy",
            "Content-Security-Policy-Report-Only", "X-Frame-Options",
            "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy",
            "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy",
            "Cross-Origin-Embedder-Policy"
        )
        security = {}
        for name in security_names:
            observed = []
            for response in responses:
                response_headers = response.get("headers", {})
                value = next((v for k, v in response_headers.items()
                              if k.lower() == name.lower()), None)
                if value:
                    observed.append({"path": response.get("path", "/"), "value": value})
            security[name] = {
                "status": "present" if observed else "not_observed",
                "observations": observed,
                "scope_note": "Not observed in tested responses is not proof of global absence."
            }
        if parsed.scheme.lower() != "https":
            security["Strict-Transport-Security"]["status"] = "not_applicable_http"

        versions = []
        for header_name in ("Server", "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version"):
            value = next((v for k, v in headers.items() if k.lower() == header_name.lower()), "")
            if value:
                match = re.search(r"\b(?:\d+\.){1,3}\d+(?:[-+][\w.-]+)?\b", value)
                if match:
                    versions.append({"component": header_name, "version": match.group(0),
                                     "source": "HTTP response header", "raw": value})
        return {
            "detections": detections, "evidence": evidence, "responses": responses,
            "tls": tls, "os_fingerprint": os_result, "security_headers": security,
            "versions": versions,
            "cdn_proxy": [d for d in detections if d["family"] == "CDN / Proxy"],
            "notes": [
                "Fingerprinting uses bounded, unauthenticated, read-only requests.",
                "A missing header is reported as not observed, not proof of absence.",
                "CDN/proxy identification describes the visible edge and may hide origin infrastructure.",
                "Technology versions are reported only when an explicit version pattern is present."
            ]
        }

    @staticmethod
    def _rdap_vcard_values(entity):
        """Return normalized vCard properties from an RDAP entity."""
        vcard = entity.get("vcardArray", [])
        props = vcard[1] if isinstance(vcard, list) and len(vcard) > 1 and isinstance(vcard[1], list) else []
        values = {}
        for prop in props:
            if isinstance(prop, list) and len(prop) >= 4:
                values[str(prop[0]).lower()] = prop[3]
        return values

    @staticmethod
    def _rdap_entity_country(address):
        """Extract only the country component from an RFC 6350 ADR value."""
        if isinstance(address, dict):
            return address.get("country-name") or address.get("country") or ""
        if isinstance(address, list):
            # vCard ADR structured value: PO box, ext, street, locality,
            # region, postal code, country.
            return address[6] if len(address) > 6 and isinstance(address[6], str) else ""
        return ""

    @staticmethod
    def _whois_query(server, domain, timeout=7):
        """Perform a bounded, read-only WHOIS TCP query."""
        connection = socket.create_connection((server, 43), timeout=timeout)
        try:
            connection.settimeout(timeout)
            connection.sendall((domain + "\r\n").encode("ascii", errors="ignore"))
            chunks = []
            total = 0
            while total < 1024 * 1024:
                chunk = connection.recv(min(16384, 1024 * 1024 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace")
        finally:
            connection.close()

    @staticmethod
    def _parse_whois_text(text, result):
        """Merge common WHOIS field labels without collecting personal contacts."""
        aliases = {
            "registrar": ("registrar", "registrar name", "sponsoring registrar"),
            "created": ("creation date", "created", "created on", "registered on", "registration date"),
            "expires": ("registry expiry date", "registrar registration expiration date",
                        "expiration date", "expiry date", "expires", "paid-till", "valid until"),
            "updated": ("updated date", "last updated", "last update", "modified"),
            "registrant_organization": ("registrant organization", "registrant organisation",
                                       "org", "organisation", "organization"),
            "registrant_country": ("registrant country", "country"),
        }
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("%", "#", ">>>")) or ":" not in line:
                continue
            label, value = line.split(":", 1)
            label = re.sub(r"\s+", " ", label.strip().lower())
            value = value.strip()
            if not value or value.lower() in ("redacted for privacy", "redacted", "not disclosed"):
                continue
            for target, names in aliases.items():
                if label in names and (not result.get(target) or result[target] in (
                    "Unknown", "Not disclosed", "Not publicly disclosed"
                )):
                    result[target] = value
                    break
            if label in ("name server", "nameserver", "nserver"):
                name = value.split()[0].rstrip(".").lower()
                if name and name not in result["nameservers"]:
                    result["nameservers"].append(name)
            if label in ("domain status", "status"):
                status = value.split()[0]
                if status and status not in result["status"]:
                    result["status"].append(status)
        return result

    def _domain_registration(self, host):
        """Resolve authoritative RDAP via IANA bootstrap, then enrich/fallback with WHOIS."""
        raw_host = (host or "").strip().lower().rstrip(".")
        if not raw_host:
            return {"error": "No domain name available."}
        try:
            # Website URLs may contain IDNs; RDAP DNS bootstrap uses ASCII labels.
            domain = raw_host.encode("idna").decode("ascii")
        except Exception:
            domain = raw_host

        result = {
            "domain": domain, "registrar": "Unknown",
            "registrant_organization": "Not publicly disclosed",
            "registrant_country": "Not publicly disclosed",
            "created": "Unknown", "expires": "Unknown", "updated": "Unknown",
            "nameservers": [], "status": [], "rdap_source": "Not found",
            "whois_source": "Not queried", "lookup_errors": []
        }

        # Try the exact host first. If it is a common www host, retry the
        # registrable-looking parent as a practical fallback for website URLs.
        candidates = [domain]
        if domain.startswith("www.") and domain.count(".") >= 2:
            candidates.append(domain[4:])

        rdap_data = None
        rdap_url = ""
        for candidate in candidates:
            try:
                bootstrap_request = urllib.request.Request(
                    "https://data.iana.org/rdap/dns.json",
                    headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/json"}
                )
                with urllib.request.urlopen(bootstrap_request, timeout=10) as response:
                    bootstrap = json.loads(response.read(2 * 1024 * 1024).decode("utf-8", errors="replace"))
                labels = candidate.lower().split(".")
                services = bootstrap.get("services", [])
                matches = []
                for service in services:
                    if not isinstance(service, list) or len(service) != 2:
                        continue
                    suffixes, urls = service
                    for suffix in suffixes:
                        suffix = str(suffix).lower().lstrip(".")
                        if candidate == suffix or candidate.endswith("." + suffix):
                            for base in urls:
                                matches.append((len(suffix), str(base)))
                if not matches:
                    result["lookup_errors"].append(f"IANA RDAP bootstrap has no service for {candidate}.")
                    continue
                base_url = sorted(matches, key=lambda item: item[0], reverse=True)[0][1]
                query_url = base_url.rstrip("/") + "/domain/" + urllib.parse.quote(candidate, safe=".-")
                request = urllib.request.Request(
                    query_url,
                    headers={"User-Agent": f"{APP_NAME}/{APP_VERSION} (domain registration lookup)",
                             "Accept": "application/rdap+json, application/json"}
                )
                with urllib.request.urlopen(request, timeout=12) as response:
                    payload = response.read(2 * 1024 * 1024)
                    rdap_data = json.loads(payload.decode("utf-8", errors="replace"))
                    rdap_url = response.geturl()
                result["domain"] = rdap_data.get("ldhName") or candidate
                result["rdap_source"] = rdap_url
                break
            except Exception as exc:
                result["lookup_errors"].append(f"RDAP {candidate}: {type(exc).__name__}: {exc}")

        if rdap_data:
            result["status"] = list(rdap_data.get("status") or [])
            for event in rdap_data.get("events", []):
                action = str(event.get("eventAction") or "").lower()
                date = event.get("eventDate") or ""
                if not date:
                    continue
                if "registration" in action:
                    result["created"] = date
                elif "expiration" in action:
                    result["expires"] = date
                elif "last changed" in action or "last update" in action:
                    result["updated"] = date

            # Registrar/registrant objects are not guaranteed to be only at
            # the first level. Walk nested entities and interpret vCard values.
            entities = []
            pending = list(rdap_data.get("entities", []) or [])
            while pending:
                entity = pending.pop(0)
                if not isinstance(entity, dict):
                    continue
                entities.append(entity)
                pending.extend(entity.get("entities", []) or [])

            for entity in entities:
                roles = [str(role).lower() for role in entity.get("roles", [])]
                values = self._rdap_vcard_values(entity)
                if "registrar" in roles and result["registrar"] == "Unknown":
                    registrar_name = values.get("fn") or values.get("org")
                    if isinstance(registrar_name, list):
                        registrar_name = " ".join(str(part) for part in registrar_name if part)
                    if not registrar_name:
                        registrar_name = entity.get("handle")
                    if registrar_name:
                        result["registrar"] = str(registrar_name).strip()
                if "registrant" in roles:
                    org = values.get("org")
                    if isinstance(org, list):
                        org = " ".join(str(part) for part in org if part)
                    if isinstance(org, str) and org.strip():
                        result["registrant_organization"] = org.strip()
                    country = self._rdap_entity_country(values.get("adr"))
                    if country:
                        result["registrant_country"] = str(country).strip()

            result["nameservers"] = sorted({
                str(item.get("ldhName")).rstrip(".").lower()
                for item in (rdap_data.get("nameservers", []) or [])
                if isinstance(item, dict) and item.get("ldhName")
            })

            # Some registries identify their registrar through a related RDAP
            # link instead of exposing a useful vCard in the domain object.
            if result["registrar"] == "Unknown":
                for link in rdap_data.get("links", []) or []:
                    if str(link.get("rel", "")).lower() == "related" and link.get("href"):
                        href = str(link["href"])
                        if "/entity/" in href:
                            try:
                                req = urllib.request.Request(
                                    href, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}",
                                                   "Accept": "application/rdap+json, application/json"}
                                )
                                with urllib.request.urlopen(req, timeout=8) as response:
                                    entity_data = json.loads(response.read(512 * 1024).decode("utf-8", errors="replace"))
                                values = self._rdap_vcard_values(entity_data)
                                name = values.get("fn") or values.get("org") or entity_data.get("handle")
                                if name:
                                    result["registrar"] = " ".join(name) if isinstance(name, list) else str(name)
                                    break
                            except Exception as exc:
                                result["lookup_errors"].append("Registrar entity lookup: " + str(exc))

        # WHOIS fallback/enrichment: many registries publish fields not included
        # in their RDAP response. Port 43 may be blocked by some networks.
        whois_text = ""
        whois_errors = []
        for candidate in candidates:
            try:
                iana_reply = self._whois_query("whois.iana.org", candidate, timeout=6)
                referral = ""
                for line in iana_reply.splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        if key.strip().lower() in ("refer", "whois"):
                            referral = value.strip()
                            break
                if referral:
                    referral = referral.split()[0]
                    whois_text = self._whois_query(referral, candidate, timeout=7)
                    result["whois_source"] = referral
                else:
                    whois_text = iana_reply
                    result["whois_source"] = "whois.iana.org"
                self._parse_whois_text(whois_text, result)
                if whois_text.strip():
                    break
            except Exception as exc:
                whois_errors.append(f"{candidate}: {type(exc).__name__}: {exc}")

        if whois_errors:
            result["whois_errors"] = whois_errors
        if not rdap_data and not whois_text:
            result["error"] = "Both authoritative RDAP and WHOIS lookups failed. Check internet access, DNS, HTTPS and outbound TCP port 43."
        elif not rdap_data:
            result["rdap_source"] = "WHOIS fallback"
        return result

    def run(self):
        report = {"target": self.start_url, "server": "Unknown", "server_family": "Unknown",
                  "powered_by": "Not disclosed", "os": "Not reliably identifiable",
                  "status": "Unknown", "final_url": self.start_url, "content_type": "Unknown",
                  "ip_addresses": [], "security_headers": {}, "cookies": [], "technologies": [],
                  "generator": "", "login_pages": [], "domain_registration": {}, "notes": []}
        try:
            if not self.start_url:
                raise ValueError("Invalid website address.")
            parsed = urllib.parse.urlsplit(self.start_url)
            host = parsed.hostname or ""
            if self._stop_requested.is_set():
                report["notes"].append("Discovery stopped by user.")
                self.result_ready.emit(report)
                return
            if self.profile:
                try:
                    report["ip_addresses"] = sorted({x[4][0] for x in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})
                except Exception:
                    report["notes"].append("DNS address lookup was unavailable.")
            if self.collect_domain and not self._stop_requested.is_set():
                self.progress.emit("Looking up public domain registration (RDAP)…")
                report["domain_registration"] = self._domain_registration(host)
            if self._stop_requested.is_set():
                report["notes"].append("Discovery stopped by user.")
                self.result_ready.emit(report)
                return
            self.progress.emit("Reading public server headers and website fingerprints…")
            try:
                home = self._request(self.start_url, "GET", 512 * 1024)
            except Exception:
                home = self._request(self.start_url, "HEAD", 0)
            headers = home["headers"]
            if self.profile:
                report["advanced_fingerprint"] = self._advanced_profile(home, parsed)
            report["status"] = str(home["status"])
            report["final_url"] = home["url"]
            html = home.get("body", b"").decode("utf-8", errors="replace")
            if self.profile:
                report["server"] = headers.get("Server", "Not disclosed")
                report["server_family"] = self._server_family(report["server"])
                report["powered_by"] = headers.get("X-Powered-By", "Not disclosed")
                report["content_type"] = headers.get("Content-Type", "Not disclosed")
                security_names = ("Strict-Transport-Security", "Content-Security-Policy",
                                  "X-Frame-Options", "X-Content-Type-Options",
                                  "Referrer-Policy", "Permissions-Policy", "Cross-Origin-Opener-Policy")
                report["security_headers"] = {n: headers.get(n, "Not present") for n in security_names}
                report["cookies"] = [v.split("=", 1)[0].strip() for k, v in headers.items()
                                     if k.lower() == "set-cookie" and v]
                report["technologies"], generator = self._detect_stack(html, headers)
                report["generator"] = generator or "Not detected"
                combined = (report["server"] + " " + report["powered_by"] + " " + generator).lower()
                if "win" in combined or "iis" in combined or "asp.net" in combined:
                    report["os"] = "Windows (hint only; not confirmed)"
                elif "ubuntu" in combined:
                    report["os"] = "Ubuntu/Linux (hint only; not confirmed)"
                elif "debian" in combined:
                    report["os"] = "Debian/Linux (hint only; not confirmed)"
                elif any(x in combined for x in ("centos", "rhel", "fedora", "red hat")):
                    report["os"] = "RHEL-family Linux (hint only; not confirmed)"
                elif any(x in combined for x in ("linux", "unix")):
                    report["os"] = "Linux/Unix (hint only; not confirmed)"
                report["notes"].append("Operating-system detection is a weak fingerprint, not a verified server OS.")
            report["notes"].append("Only public unauthenticated HTTP requests were made; no passwords or exploit tests.")
            origin = f"{parsed.scheme}://{parsed.netloc}"
            for index, path in enumerate(self.LOGIN_PATHS if self.find_admin else (), 1):
                if self._stop_requested.is_set():
                    report["notes"].append("Discovery stopped by user.")
                    break
                self.progress.emit(f"Checking common login routes {index}/{len(self.LOGIN_PATHS)}…")
                target = urllib.parse.urljoin(origin + "/", path.lstrip("/"))
                try:
                    result = self._request(target, "GET", 64 * 1024)
                except Exception:
                    continue
                if (urllib.parse.urlsplit(result["url"]).hostname or "").lower() != host.lower():
                    continue
                code = int(result["status"])
                if code not in (200, 201, 202, 204, 301, 302, 303, 307, 308, 401, 403, 405):
                    continue
                body = result.get("body", b"").decode("utf-8", errors="ignore").lower()
                location = result["headers"].get("Location", "")
                looks_login = any(x in body for x in ("password", "log in", "login", "sign in", "username", "wp-login"))
                if code in (200, 201, 202) and not looks_login and not location:
                    continue
                report["login_pages"].append({"url": result["url"], "status": code,
                    "classification": "Login/admin candidate" if looks_login or code in (401, 403) else "Possible management route",
                    "redirect": location})
            self.result_ready.emit(report)
        except Exception as exc:
            report["notes"].append("Scan error: " + str(exc))
            self.result_ready.emit(report)


class AdminLoginFinderDialog(QDialog):
    def __init__(self, parent=None, initial_url=""):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Admin / Login Finder & Server Profiler")
        self.resize(900, 680)
        self.worker = None
        layout = QVBoxLayout(self)
        note = QLabel("For websites you own or are authorized to assess. Checks public login routes and exposed server metadata only.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.url_input = QLineEdit(initial_url)
        self.url_input.setPlaceholderText("https://example.com")
        row.addWidget(self.url_input, 1)
        self.scan_button = QPushButton("Start discovery")
        self.scan_button.clicked.connect(self.start_scan)
        row.addWidget(self.scan_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.status = QLabel("Ready.")
        layout.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Server profile and discovered login routes will appear here.")
        layout.addWidget(self.output, 1)
        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy report")
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.output.toPlainText()))
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def start_scan(self):
        url = WebsiteScanWorker.prepare_url(self.url_input.text())
        if not url or not urllib.parse.urlsplit(url).netloc:
            QMessageBox.warning(self, "Invalid address", "Enter a valid website URL.")
            return
        self.url_input.setText(url)
        self.output.clear()
        self.scan_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("Starting…")
        self.worker = AdminLoginFinderWorker(url)
        self.worker.progress.connect(self.status.setText)
        self.worker.result_ready.connect(self.show_report)
        self.worker.start()

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.status.setText("Stopping discovery… current network request may take a few seconds to finish.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.status.setText("Discovery is still running; wait for it to finish before closing.")
            event.ignore()
            return
        event.accept()

    def show_report(self, report):
        lines = [f"{APP_NAME.upper()} ADMIN / LOGIN FINDER & SERVER PROFILE", "=" * 58,
                 f"Target: {report.get('target')}", f"Final URL: {report.get('final_url')}",
                 f"HTTP status: {report.get('status')}",
                 f"Public IP address(es): {', '.join(report.get('ip_addresses', [])) or 'Unknown'}",
                 "", "SERVER / PLATFORM", f"Web server: {report.get('server_family')}",
                 f"Server header: {report.get('server')}", f"X-Powered-By: {report.get('powered_by')}",
                 f"Operating system: {report.get('os')}", f"Content-Type: {report.get('content_type')}",
                 f"CMS / frameworks: {', '.join(report.get('technologies', [])) or 'Not detected'}",
                 f"HTML generator: {report.get('generator')}", "", "SECURITY-RELATED RESPONSE HEADERS"]
        for name, value in report.get("security_headers", {}).items():
            lines.append(f"{name}: {value}")
        advanced = report.get("advanced_fingerprint", {})
        if advanced:
            lines += ["", "ADVANCED TECHNOLOGY & SECURITY FINGERPRINTING",
                      "OS fingerprint: " + advanced.get("os_fingerprint", {}).get("value", "Unknown"),
                      "OS confidence: " + advanced.get("os_fingerprint", {}).get("confidence", "Unknown")]
            tls = advanced.get("tls", {})
            lines += ["TLS status: " + tls.get("status", "Unknown")]
            for key in ("tls_version", "cipher", "subject", "issuer", "not_after"):
                if tls.get(key):
                    lines.append(f"TLS {key}: {tls[key]}")
            lines += ["", "TECHNOLOGY DETECTIONS"]
            for item in advanced.get("detections", []):
                lines.append(f"{item['family']}: {item['technology']} — {item['confidence']} ({item['score']}/100)")
                for ev in item.get("evidence", []):
                    lines.append(f"    Evidence: {ev['source']} | {ev['detail']}")
            if not advanced.get("detections"):
                lines.append("No technology fingerprint reached the reporting threshold.")
            lines += ["", "SECURITY HEADERS BY TESTED PATH"]
            for name, item in advanced.get("security_headers", {}).items():
                lines.append(f"{name}: {item.get('status')}")
                for observation in item.get("observations", []):
                    lines.append(f"    {observation['path']}: {observation['value']}")
            lines += ["", "HTTP RESPONSE PATHS"]
            for item in advanced.get("responses", []):
                lines.append(f"{item.get('path')}: HTTP {item.get('status', 'not checked')} → {item.get('final_url', item.get('error', ''))}")
            lines += ["", "ADVANCED FINGERPRINT NOTES"]
            lines += ["• " + note for note in advanced.get("notes", [])]
        registration = report.get("domain_registration", {})
        if registration:
            lines += ["", "DOMAIN REGISTRATION (AUTHORITATIVE RDAP / WHOIS)",
                      f"Domain: {registration.get('domain', 'Unknown')}",
                      f"Registrar: {registration.get('registrar', 'Unknown')}",
                      f"Registrant organization: {registration.get('registrant_organization', 'Not publicly disclosed')}",
                      f"Registrant country: {registration.get('registrant_country', 'Not publicly disclosed')}",
                      f"Created: {registration.get('created', 'Unknown')}",
                      f"Expires: {registration.get('expires', 'Unknown')}",
                      f"Last updated: {registration.get('updated', 'Unknown')}",
                      f"Nameservers: {', '.join(registration.get('nameservers', [])) or 'Unknown'}",
                      f"Domain status: {', '.join(registration.get('status', [])) or 'Unknown'}",
                      f"RDAP source: {registration.get('rdap_source', 'Unknown')}",
                      f"WHOIS source: {registration.get('whois_source', 'Not queried')}"]
            if registration.get("error"):
                lines.append(registration["error"])
            for lookup_error in registration.get("lookup_errors", []):
                lines.append("RDAP note: " + lookup_error)
            for whois_error in registration.get("whois_errors", []):
                lines.append("WHOIS note: " + whois_error)
            lines.append("Note: Personal registrant names, email addresses, phone numbers and street addresses are intentionally not collected; privacy-protected fields may not be public.")
        lines += ["", "COOKIE NAMES (values are not collected)"]
        lines += report.get("cookies", []) or ["No Set-Cookie header observed."]
        lines += ["", f"LOGIN / ADMIN ROUTES ({len(report.get('login_pages', []))})"]
        for item in report.get("login_pages", []):
            lines.append(f"[HTTP {item['status']}] {item['classification']} — {item['url']}")
            if item.get("redirect"):
                lines.append(f"    Redirect: {item['redirect']}")
        if not report.get("login_pages"):
            lines.append("No common login/admin routes were confirmed.")
        lines += ["", "NOTES"] + ["• " + note for note in report.get("notes", [])]
        self.output.setPlainText("\n".join(lines))
        self.status.setText("Discovery stopped." if any("stopped by user" in n.lower() for n in report.get("notes", [])) else "Discovery complete.")
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)


class WebsiteDownloaderDialog(QWidget):
    """Scan a website, review discovered files, and queue only user-selected items."""
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.worker = None
        self.recon_worker = None
        self.recon_dialog = None
        self.recon_report = None
        layout = QVBoxLayout(self)
        intro = QLabel("Scan accessible pages and resources. You can also discover public login/admin routes and profile server technologies. Use only on sites you own or are authorized to assess.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        self.url_input.setMinimumHeight(36)
        url_row.addWidget(self.url_input, 1)
        self.scan_button = QPushButton("Scan website")
        self.scan_button.clicked.connect(self.start_scan)
        url_row.addWidget(self.scan_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)
        url_row.addWidget(self.stop_button)
        self.skip_button = QPushButton("Skip current page")
        self.skip_button.setEnabled(False)
        self.skip_button.clicked.connect(self.skip_current_page)
        url_row.addWidget(self.skip_button)
        self.finder_button = QPushButton("Admin / Login Finder")
        self.finder_button.clicked.connect(self.open_finder)
        url_row.addWidget(self.finder_button)
        self.view_recon_button = QPushButton("View discovery results")
        self.view_recon_button.setEnabled(False)
        self.view_recon_button.clicked.connect(self.open_recon_results)
        url_row.addWidget(self.view_recon_button)
        layout.addLayout(url_row)

        options = QHBoxLayout()
        options.addWidget(QLabel("Scan scope:"))
        self.scope = QComboBox()
        self.scope.addItem("Only this domain", False)
        self.scope.addItem("Include linked external domains / CDN", True)
        self.scope.setMinimumWidth(280)
        options.addWidget(self.scope)
        options.addWidget(QLabel("Max pages:"))
        self.max_pages = QComboBox()
        self.max_pages.addItems(["100", "250", "500", "1000"])
        self.max_pages.setCurrentText("500")
        options.addWidget(self.max_pages)
        options.addStretch(1)
        layout.addLayout(options)
        recon_options = QHBoxLayout()
        self.find_admin_checkbox = QCheckBox("Find admin/login pages")
        self.profile_checkbox = QCheckBox("Profile server / OS / technologies")
        self.domain_checkbox = QCheckBox("Domain registrar / registration info (RDAP)")
        recon_options.addWidget(self.find_admin_checkbox)
        recon_options.addWidget(self.profile_checkbox)
        recon_options.addWidget(self.domain_checkbox)
        recon_options.addStretch(1)
        layout.addLayout(recon_options)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("File types found (select categories):"))
        self.category_checks = {}
        self.category_counts = {}
        self.category_filter_layout = QHBoxLayout()
        filter_row.addLayout(self.category_filter_layout, 1)
        filter_row.addWidget(QLabel("Extension:"))
        self.extension_filter = QComboBox()
        self.extension_filter.addItem("All extensions")
        self.extension_filter.currentTextChanged.connect(self.apply_filters)
        filter_row.addWidget(self.extension_filter)
        layout.addLayout(filter_row)

        self.status = QLabel("No scan started.")
        layout.addWidget(self.status)
        self.total_size_label = QLabel("Found: 0 files | Known total size: 0 B")
        layout.addWidget(self.total_size_label)
        self.results = QTableWidget(0, 5)
        self.results.setHorizontalHeaderLabels(["Download", "File name", "Type", "Size", "URL"])
        self.results.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self.copy_result_url)
        self.results.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.results.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.results, 1)

        buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self.set_all_checked(True))
        self.clear_button = QPushButton("Clear selection")
        self.clear_button.clicked.connect(lambda: self.set_all_checked(False))
        self.copy_url_button = QPushButton("Copy selected URL")
        self.copy_url_button.clicked.connect(self.copy_result_url)
        self.download_button = QPushButton("Download selected")
        self.download_button.clicked.connect(self.download_selected)
        self.download_button.setEnabled(False)
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.copy_url_button)
        buttons.addWidget(self.download_button)
        layout.addLayout(buttons)

    def start_scan(self):
        url = WebsiteScanWorker.prepare_url(self.url_input.text())
        parsed = urllib.parse.urlsplit(url)
        if not url or parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid address", "Enter a valid website address, for example example.com.")
            return
        self.url_input.setText(url)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        self.results.setRowCount(0)
        self.total_size_label.setText("Found: 0 files | Known total size: 0 B")
        self.category_counts.clear()
        self.category_checks.clear()
        while self.category_filter_layout.count():
            item = self.category_filter_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.extension_filter.blockSignals(True)
        self.extension_filter.clear()
        self.extension_filter.addItem("All extensions")
        self.extension_filter.blockSignals(False)
        self.download_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        self.status.setText("Starting scan…")
        self.worker = WebsiteScanWorker(url, self.scope.currentData(), int(self.max_pages.currentText()))
        self.worker.found.connect(self.add_result)
        if self.find_admin_checkbox.isChecked() or self.profile_checkbox.isChecked() or self.domain_checkbox.isChecked():
            self.start_recon(url)
        self.worker.progress.connect(self.status.setText)
        self.worker.finished_scan.connect(self.scan_finished)
        self.worker.failed_scan.connect(self.scan_failed)
        self.worker.start()

    def open_finder(self):
        dialog = AdminLoginFinderDialog(self, self.url_input.text().strip())
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.show()
        self.recon_dialog = dialog

    def start_recon(self, url):
        if self.recon_worker and self.recon_worker.isRunning():
            return
        self.recon_dialog = None
        self.recon_report = None
        self.view_recon_button.setEnabled(False)
        self.recon_worker = AdminLoginFinderWorker(
            url, find_admin=self.find_admin_checkbox.isChecked(),
            profile=self.profile_checkbox.isChecked(),
            collect_domain=self.domain_checkbox.isChecked()
        )
        self.recon_worker.progress.connect(self.status.setText)
        self.recon_worker.result_ready.connect(self.on_recon_result)
        self.recon_worker.start()

    def on_recon_result(self, report):
        self.recon_report = report
        self.view_recon_button.setEnabled(True)
        self.status.setText("Discovery data is ready. Click 'View discovery results' whenever you want.")

    def open_recon_results(self):
        if not self.recon_report:
            QMessageBox.information(self, "No results yet", "Run a scan with at least one discovery option enabled first.")
            return
        dialog = AdminLoginFinderDialog(self, self.url_input.text().strip())
        dialog.scan_button.hide()
        dialog.stop_button.hide()
        dialog.url_input.hide()
        dialog.show_report(self.recon_report)
        dialog.setWindowTitle(f"{APP_NAME} — Saved discovery results")
        dialog.exec()

    def skip_current_page(self):
        if self.worker and self.worker.isRunning():
            self.worker.skip_current_page()
            self.status.setText("Skip requested — the current page will be ignored after its active request finishes.")

    def copy_result_url(self, position=None):
        row = self.results.currentRow()
        if position is not None:
            item = self.results.itemAt(position)
            if item:
                row = item.row()
        url_item = self.results.item(row, 4) if row >= 0 else None
        if url_item:
            QApplication.clipboard().setText(url_item.text())
            self.status.setText("File URL copied to clipboard.")

    def stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.skip_button.setEnabled(False)
            self.status.setText("Stopping scan…")

    def add_result(self, url, name, content_type, size):
        row = self.results.rowCount()
        self.results.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        check.setCheckState(Qt.Unchecked)
        check.setData(Qt.UserRole, url)
        self.results.setItem(row, 0, check)
        name_item = QTableWidgetItem(name)
        ext = os.path.splitext(name.lower())[1] or "(no extension)"
        name_item.setData(Qt.UserRole, ext)
        self.results.setItem(row, 1, name_item)
        self.results.setItem(row, 2, QTableWidgetItem(content_type))
        size_item = QTableWidgetItem(format_bytes(size) if size >= 0 else "Unknown")
        size_item.setData(Qt.UserRole, size)
        self.results.setItem(row, 3, size_item)
        self.results.setItem(row, 4, QTableWidgetItem(url))
        self.update_total_size()
        category = self.file_category(name, content_type)
        self.category_counts[category] = self.category_counts.get(category, 0) + 1
        if category not in self.category_checks:
            category_box = QCheckBox()
            category_box.setChecked(True)
            category_box.stateChanged.connect(self.apply_filters)
            self.category_checks[category] = category_box
            self.category_filter_layout.addWidget(category_box)
        self.category_checks[category].setText(f"{category} ({self.category_counts[category]})")
        existing = [self.extension_filter.itemText(i) for i in range(self.extension_filter.count())]
        if ext not in existing:
            self.extension_filter.addItem(ext)
        self.apply_filters()

    @staticmethod
    def file_category(name, content_type):
        ext = os.path.splitext(name.lower())[1]
        mime = (content_type or "").lower()
        groups = {
            "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tif", ".tiff", ".avif"},
            "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpeg", ".mpg", ".3gp"},
            "Audio": {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"},
            "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".csv"},
            "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
            "Programs": {".exe", ".msi", ".apk", ".dmg", ".deb", ".rpm", ".jar", ".appimage"},
            "Web files": {".html", ".htm", ".css", ".js", ".mjs", ".json", ".xml", ".woff", ".woff2", ".ttf", ".otf"}
        }
        for category, extensions in groups.items():
            if ext in extensions:
                return category
        if mime.startswith("image/"): return "Images"
        if mime.startswith("video/"): return "Video"
        if mime.startswith("audio/"): return "Audio"
        if mime in ("application/pdf",): return "Documents"
        if mime.startswith(("application/zip", "application/x-rar", "application/x-7z")): return "Archives"
        if mime.startswith(("text/", "application/javascript", "application/json")): return "Web files"
        return "Other"

    def update_total_size(self):
        count = self.results.rowCount()
        known_total = sum(
            max(0, int(self.results.item(row, 3).data(Qt.UserRole) or 0))
            for row in range(count) if self.results.item(row, 3)
        )
        known_count = sum(
            1 for row in range(count)
            if self.results.item(row, 3) and int(self.results.item(row, 3).data(Qt.UserRole) or -1) >= 0
        )
        self.total_size_label.setText(
            f"Found: {count} files | Known total size: {format_bytes(known_total)} "
            f"({known_count} sizes known)"
        )

    def apply_filters(self):
        selected_categories = {
            category for category, checkbox in self.category_checks.items()
            if checkbox.isChecked()
        }
        extension = self.extension_filter.currentText()
        for row in range(self.results.rowCount()):
            name_item = self.results.item(row, 1)
            type_item = self.results.item(row, 2)
            row_ext = name_item.data(Qt.UserRole) if name_item else ""
            row_category = self.file_category(name_item.text() if name_item else "",
                                              type_item.text() if type_item else "")
            visible = row_category in selected_categories
            visible = visible and (extension == "All extensions" or extension == row_ext)
            self.results.setRowHidden(row, not visible)

    def scan_finished(self, count):
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.download_button.setEnabled(count > 0)
        stopped = self.worker and self.worker._stop.is_set()
        self.status.setText(
            f"Scan stopped: {count} files found. Select the files you want."
            if stopped else
            f"Scan complete: {count} unique downloadable links found. Select the files you want."
        )

    def scan_failed(self, message):
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.status.setText(f"Scan error: {message}")

    def set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.results.rowCount()):
            if not self.results.isRowHidden(row):
                self.results.item(row, 0).setCheckState(state)

    def download_selected(self):
        urls = []
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                urls.append((item.data(Qt.UserRole), self.results.item(row, 1).text()))
        if not urls:
            QMessageBox.information(self, "Nothing selected", "Select at least one file to download.")
            return
        parsed = urllib.parse.urlsplit(WebsiteScanWorker.prepare_url(self.url_input.text()))
        site_name = re.sub(r"[^A-Za-z0-9._-]+", "_", parsed.hostname or "website").strip("._-") or "website"
        base_folder = self.main_window.folder.text().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        site_folder = os.path.join(base_folder, site_name)
        os.makedirs(site_folder, exist_ok=True)
        added = self.main_window.add_website_downloads(urls, site_folder)
        self.status.setText(f"Queued {added} selected files in: {site_folder}")
        self.main_window.status.setText(f"Website files queued: {added} → {site_folder}")
        self.main_window.tabs.setCurrentIndex(0)





class DownloadLinkParser(HTMLParser):
    """Collect candidate download links from ordinary HTML pages."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        candidates = []
        if tag.lower() == "a":
            candidates.append(values.get("href"))
            if values.get("download"):
                self.links.append((values.get("href"), values.get("download")))
        if tag.lower() in ("audio", "video", "source", "track"):
            candidates.extend((values.get("src"), values.get("href")))
        if tag.lower() == "link":
            candidates.append(values.get("href"))
        for value in candidates:
            if value:
                self.links.append((value, ""))


class LinkGrabberWorker(QThread):
    """Discover HTTP(S) download resources using Website Scan URL handling."""
    results_ready = Signal(list)
    failed = Signal(str)

    DOWNLOAD_EXTENSIONS = {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
        ".exe", ".msi", ".msix", ".apk", ".dmg", ".deb", ".rpm", ".jar",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".mp3", ".wav", ".flac", ".mp4", ".mkv", ".avi", ".mov", ".webm",
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".csv", ".txt"
    }

    def __init__(self, page_url):
        super().__init__()
        self.page_url = WebsiteScanWorker.prepare_url(page_url)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8"
        }

    @staticmethod
    def normalize_url(url):
        return WebsiteScanWorker.normalize_url(url)

    @staticmethod
    def protocol_candidates(url):
        parsed = urllib.parse.urlsplit(url)
        alternate = "http" if parsed.scheme.lower() == "https" else "https"
        other = urllib.parse.urlunsplit(
            (alternate, parsed.netloc, parsed.path, parsed.query, "")
        )
        return [url, other]

    def fetch_page(self):
        last_error = None
        for candidate in self.protocol_candidates(self.page_url):
            try:
                request = urllib.request.Request(candidate, headers=self.headers)
                with urllib.request.urlopen(request, timeout=20) as response:
                    content_type = response.headers.get("Content-Type", "").lower()
                    if content_type and "html" not in content_type and "xhtml" not in content_type:
                        raise ValueError("The supplied URL does not appear to be an HTML page.")
                    raw = response.read(5 * 1024 * 1024 + 1)
                    if len(raw) > 5 * 1024 * 1024:
                        raise ValueError("Page is larger than the 5 MB scan limit.")
                    charset = response.headers.get_content_charset() or "utf-8"
                    final_url = self.normalize_url(response.geturl())
                    return final_url, raw.decode(charset, errors="replace")
            except Exception as exc:
                last_error = exc
        raise last_error or OSError("Unable to open webpage using HTTP or HTTPS.")

    def probe_download(self, url):
        """Resolve redirects and identify extensionless files by response MIME type."""
        for candidate in self.protocol_candidates(url):
            for method in ("HEAD", "GET"):
                try:
                    request = urllib.request.Request(candidate, headers=self.headers, method=method)
                    with urllib.request.urlopen(request, timeout=9) as response:
                        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                        final_url = self.normalize_url(response.geturl()) or candidate
                        if method == "GET":
                            response.read(2048)
                        if content_type and not (
                            content_type.startswith("text/html")
                            or content_type in ("application/xhtml+xml",)
                        ):
                            return final_url, content_type
                        if content_type:
                            return final_url, content_type
                except Exception:
                    continue
        return url, ""

    def run(self):
        try:
            if not self.page_url:
                raise ValueError("Enter a valid HTTP or HTTPS webpage URL.")
            final_url, html = self.fetch_page()
            parser = DownloadLinkParser()
            parser.feed(html)

            # Include downloadable resources referenced from inline CSS.
            for value in re.findall(r"""url\(['"]?(.*?)['"]?\)""", html, flags=re.I):
                value = value.strip().strip(" '\"")
                if value and not value.lower().startswith("data:"):
                    parser.links.append((value, ""))

            candidates = {}
            for raw_url, suggested in parser.links:
                if not raw_url:
                    continue
                raw_url = raw_url.strip()
                # urljoin handles relative paths and //cdn.example/... protocol-relative URLs.
                absolute = self.normalize_url(urllib.parse.urljoin(final_url, raw_url))
                if not absolute or absolute == final_url:
                    continue
                parsed = urllib.parse.urlsplit(absolute)
                path = urllib.parse.unquote(parsed.path)
                name = os.path.basename(path) or suggested or "Download"
                extension = os.path.splitext(path.lower())[1]
                if extension in self.DOWNLOAD_EXTENSIONS or suggested:
                    candidates.setdefault(absolute, name)
                elif not extension:
                    candidates.setdefault(absolute, name)

            found = {}
            extensionless = []
            for url, name in candidates.items():
                path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).lower()
                if os.path.splitext(path)[1] in self.DOWNLOAD_EXTENSIONS:
                    found[url] = name
                else:
                    extensionless.append((url, name))

            # Probe extensionless links concurrently, just like Website Scan.
            with ThreadPoolExecutor(max_workers=12) as pool:
                futures = {pool.submit(self.probe_download, url): (url, name)
                           for url, name in extensionless}
                for future in as_completed(futures):
                    original, name = futures[future]
                    try:
                        checked_url, content_type = future.result()
                    except Exception:
                        continue
                    if not content_type or content_type.startswith("text/html") or content_type == "application/xhtml+xml":
                        continue
                    parsed = urllib.parse.urlsplit(checked_url)
                    final_name = os.path.basename(urllib.parse.unquote(parsed.path)) or name
                    if not os.path.splitext(final_name)[1]:
                        guessed = mimetypes.guess_extension(content_type)
                        if guessed:
                            final_name += guessed
                    found.setdefault(checked_url, final_name)

            self.results_ready.emit(sorted(
                ((url, name) for url, name in found.items()),
                key=lambda item: (item[1].lower(), item[0].lower())
            ))
        except Exception as exc:
            self.failed.emit(str(exc))



def _is_installed_windows_build():
    """Return True only for the packaged app installed under Program Files."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    program_files = os.environ.get("ProgramFiles")
    if not program_files:
        return False
    root = os.path.normcase(os.path.abspath(program_files))
    executable = os.path.normcase(os.path.abspath(sys.executable))
    try:
        return os.path.commonpath([root, executable]) == root
    except ValueError:
        return False


def _version_key(value):
    numbers = [int(item) for item in re.findall(r"\d+", str(value))[:3]]
    return tuple((numbers + [0, 0, 0])[:3])


class GitHubUpdateWorker(QThread):
    """Fetch release metadata only; downloading starts after explicit user approval."""
    update_available = Signal(str, str, str, str, int, str)
    up_to_date = Signal(str)
    failed = Signal(str)
    RELEASE_API = "https://api.github.com/repos/meicamghe/FDMX/releases/latest"

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            request = urllib.request.Request(
                self.RELEASE_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{APP_NAME}/{APP_VERSION}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with open_url(request, timeout=25) as response:
                release = json.loads(response.read().decode("utf-8"))
            version = str(release.get("tag_name", "")).lstrip("vV").strip()
            if not version:
                raise RuntimeError("GitHub returned a release without a version tag.")
            if _version_key(version) <= _version_key(self.current_version):
                self.up_to_date.emit(version)
                return

            release_url = release.get("html_url") or "https://github.com/meicamghe/FDMX/releases/latest"
            notes = str(release.get("body") or "").strip()
            if notes:
                # GitHub release bodies may contain literal escaped newlines.
                notes = (
                    notes.replace("\\r\\n", "\n")
                    .replace("\\n", "\n")
                    .replace("\\r", "\n")
                )
            else:
                # Keep the in-app updater useful even when a release has no body.
                notes = (
                    "Highlights:\n"
                    "- Configurable download parts (1–16 connections).\n"
                    "- Safer resume behavior for interrupted multi-part downloads.\n"
                    "- Improved update installation and verification flow.\n"
                    "- Linux package and application icon consistency updates.\n"
                    "- Windows and Linux build and packaging improvements."
                )
            asset_url = ""
            asset_size = 0
            asset_digest = ""
            if _is_installed_windows_build():
                setup = next(
                    (asset for asset in release.get("assets", [])
                     if str(asset.get("name", "")).lower().endswith(".exe")
                     and "setup" in str(asset.get("name", "")).lower()),
                    None,
                )
                if not setup or not setup.get("browser_download_url"):
                    raise RuntimeError("The latest GitHub Release does not contain a Windows Setup installer.")
                asset_url = str(setup["browser_download_url"])
                asset_size = int(setup.get("size") or 0)
                asset_digest = str(setup.get("digest") or "")
            self.update_available.emit(version, notes, release_url, asset_url, asset_size, asset_digest)
        except Exception as exc:
            self.failed.emit(str(exc))


class GitHubUpdateDownloadWorker(QThread):
    """Download and verify the installer while reporting live progress."""
    progress = Signal(int, int, float)
    downloaded = Signal(str)
    failed = Signal(str)
    canceled = Signal()

    def __init__(self, url, expected_size=0, expected_digest=""):
        super().__init__()
        self.url = url
        self.expected_size = max(0, int(expected_size or 0))
        self.expected_digest = str(expected_digest or "")
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        installer_path = ""
        try:
            fd, installer_path = tempfile.mkstemp(prefix="gns-downloader-update-", suffix=".exe")
            os.close(fd)
            request = urllib.request.Request(
                self.url,
                headers={
                    "User-Agent": f"{APP_NAME}/{APP_VERSION}",
                    "Accept": "application/octet-stream",
                },
            )
            digest = hashlib.sha256()
            downloaded = 0
            started = time.monotonic()
            with open_url(request, timeout=60) as response, open(installer_path, "wb") as output:
                raw_total = response.headers.get("Content-Length", "")
                total = int(raw_total) if raw_total.isdigit() else self.expected_size
                self.progress.emit(0, total, 0.0)
                while True:
                    if self.cancel_event.is_set():
                        raise InterruptedError("Update download canceled by user.")
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    elapsed = max(0.001, time.monotonic() - started)
                    self.progress.emit(downloaded, total, downloaded / elapsed)
            if self.cancel_event.is_set():
                raise InterruptedError("Update download canceled by user.")
            if self.expected_size and downloaded != self.expected_size:
                raise RuntimeError("The downloaded installer size does not match the GitHub release asset.")
            if self.expected_digest.startswith("sha256:"):
                expected = self.expected_digest.split(":", 1)[1].lower()
                if digest.hexdigest().lower() != expected:
                    raise RuntimeError("The installer SHA-256 digest does not match the GitHub release.")
            self.downloaded.emit(installer_path)
            installer_path = ""
        except InterruptedError:
            self.canceled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if installer_path and os.path.exists(installer_path):
                try:
                    os.remove(installer_path)
                except OSError:
                    pass



class FDMX(QWidget):
    browser_download_requested = Signal(str)
    def __init__(self):
        super().__init__()
        # Use the application's own title-bar controls; hide the native Windows frame buttons.
        self.setWindowFlags(Qt.Window)
        self._startup_started = _MODULE_STARTED_AT
        self._log_startup_stage("window construction started")
        self.setWindowTitle(f"{APP_NAME}  •  Download Manager {APP_VERSION}")
        self.setWindowIcon(self.create_app_icon())
        self.resize(1080, 680)
        self.setMinimumSize(820, 520)
        self.tasks = {}
        self.workers = {}
        self.detail_windows = {}
        self.history = []
        self._loading = False
        self._speed_samples = []  # Rolling speed samples used by the Analytics panel.
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(APP_NAME)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.current_filter = "All downloads"
        self.grabber_worker = None
        self.grabber_results = []
        self.search_query = ""
        self.load_history()
        self.load_tasks()
        self._log_startup_stage("task history restored")
        self.build_ui()
        self._log_startup_stage("interface built")
        self.load_preferences()
        self._log_startup_stage("preferences loaded")
        self.browser_download_requested.connect(self.add_download_from_browser)
        self.start_browser_bridge()
        self._log_startup_stage("browser bridge initialized")
        QApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self.refresh_table()
        self.scheduler_timer = self.startTimer(400)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.save_tasks)
        self.autosave_timer.start(5000)
        self.prompt_recovery()
        self.start_queue()
        self._log_startup_stage("startup complete")

    def _log_startup_stage(self, stage):
        """Record startup timings to help diagnose slow first launches."""
        try:
            folder = os.path.join(os.path.expanduser("~"), ".fdmx")
            os.makedirs(folder, exist_ok=True)
            elapsed = time.perf_counter() - getattr(self, "_startup_started", _MODULE_STARTED_AT)
            with open(os.path.join(folder, "startup.log"), "a", encoding="utf-8") as log:
                log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} | {elapsed:.3f}s | {stage}\n")
        except OSError:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_first_show_logged", False):
            self._first_show_logged = True
            self._log_startup_stage("main window shown")

    def create_app_icon(self):
        """Create the red G brand mark used by the app window and tray."""
        pixmap = QPixmap(256, 256)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(8, 8, 240, 240, 44, 44)
        painter.setPen(QColor("#e2231a"))
        painter.setFont(QFont("DejaVu Sans", 184, QFont.Bold))
        painter.drawText(pixmap.rect().adjusted(0, -3, 0, 0), Qt.AlignCenter, "G")
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
            QWidget { font-family: "Segoe UI", Arial, sans-serif; font-size: 11pt; }
            QLineEdit, QSpinBox, QDateTimeEdit, QComboBox { padding: 7px 9px; min-height: 30px; font-size: 11pt; }
            QPushButton { padding: 7px 13px; min-height: 32px; font-size: 10.5pt; font-weight: 600; }
            QPushButton:hover { background: #dff4e7; }
            QTableWidget { gridline-color: #d9d9d9; }
            QHeaderView::section { padding: 8px 10px; font-size: 10.5pt; font-weight: 600; }
            QProgressBar { min-height: 16px; max-height: 16px; text-align: center; }
        """)

        self.menu_bar = QMenuBar(self)
        file_menu = self.menu_bar.addMenu("File")
        file_menu.addAction("Add download", lambda: self.url.setFocus())
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        download_menu = self.menu_bar.addMenu("Download")
        for label, callback in (
            ("Start queue", self.start_queue), ("Pause selected", self.pause_selected),
            ("Resume selected", self.resume_selected), ("Cancel selected", self.cancel_selected),
            ("Retry selected", self.retry_selected), ("Remove from list", self.remove_selected),
            ("Delete file from disk", self.delete_file_selected),
        ):
            download_menu.addAction(label, callback)

        view_menu = self.menu_bar.addMenu("View")
        filter_menu = view_menu.addMenu("Show")
        self.nav_buttons = {}
        for label in ("All downloads", "In progress", "Queue", "Completed", "Failed"):
            filter_menu.addAction(label, lambda checked=False, name=label: self.set_filter(name))
        category_menu = view_menu.addMenu("File category")
        for label in ("Video", "Audio", "Documents", "Compressed", "Python", "Programs", "Images", "Spreadsheets", "Code", "Other"):
            category_menu.addAction(label, lambda checked=False, name=label: self.set_filter("Category:" + name))

        tools_menu = self.menu_bar.addMenu("Tools")
        tools_menu.addAction("Add torrent file…", self.add_torrent_file)
        tools_menu.addAction("Website Downloader…", self.open_website_downloader)
        tools_menu.addAction("Read URL from clipboard", self.paste_clipboard_url)
        tools_menu.addAction("Export report (CSV / JSON)…", self.export_analytics_report)
        tools_menu.addAction("Verify SHA-256…", self.calculate_hash)
        tools_menu.addSeparator()
        settings_menu = self.menu_bar.addMenu("Settings")
        settings_menu.addAction("Preferences…", self.open_settings_dialog)
        help_menu = self.menu_bar.addMenu("Help")
        help_menu.addAction("Check for updates…", self.check_for_updates)
        help_menu.addAction(f"About {APP_NAME}", self.show_about)
        root.setMenuBar(self.menu_bar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        downloads_page = QWidget()
        downloads_layout = QVBoxLayout(downloads_page)
        downloads_layout.setContentsMargins(0, 0, 0, 0)
        downloads_layout.setSpacing(7)
        self.tabs.addTab(downloads_page, "Downloads")

        top = QHBoxLayout()
        brand = QLabel(f"<b>G</b>  GNS Downloader  <span style='color:#777'>v{APP_VERSION}</span>")
        brand.setStyleSheet("font-size:16pt;font-weight:600;")
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
        downloads_layout.addLayout(top)

        toolbar = QHBoxLayout()
        for label, callback in (
            ("Add URL", lambda: self.url.setFocus()), ("Start", self.start_queue),
            ("Pause", self.pause_selected), ("Resume", self.resume_selected),
            ("Cancel", self.cancel_selected), ("Remove", self.remove_selected),
            ("Delete from disk", self.delete_file_selected), ("Open folder", self.open_folder),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        self.clipboard_monitor = QCheckBox("Clipboard Monitor")
        self.clipboard_monitor.setToolTip("Detect copied HTTP/HTTPS links and place them in the URL field; downloads never start automatically.")
        self.clipboard_monitor.toggled.connect(self.save_preferences)
        toolbar.addWidget(self.clipboard_monitor)
        toolbar.addStretch(1)
        downloads_layout.addLayout(toolbar)

        entry = QGridLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste HTTP, HTTPS, or magnet link here…")
        self.folder = QLineEdit(os.path.join(os.path.expanduser("~"), "Downloads"))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.select_folder)
        self.add_button = QPushButton("Start Download")
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
        downloads_layout.addLayout(entry)

        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle(f"{APP_NAME} Preferences")
        self.settings_dialog.setMinimumWidth(430)
        settings_layout = QVBoxLayout(self.settings_dialog)
        settings_grid = QGridLayout()
        settings_grid.addWidget(QLabel("Maximum simultaneous downloads:"), 0, 0)
        self.max_downloads = QSpinBox()
        self.max_downloads.setRange(1, 16)
        self.max_downloads.setValue(8)
        settings_grid.addWidget(self.max_downloads, 0, 1)
        settings_grid.addWidget(QLabel("Download parts per file (1–16):"), 1, 0)
        self.parts_count = QSpinBox()
        self.parts_count.setRange(1, MAX_PARTS)
        self.parts_count.setValue(CONNECTIONS)
        self.parts_count.setToolTip("Fixed number of parallel connections for each file; default is 8.")
        settings_grid.addWidget(self.parts_count, 1, 1)
        settings_grid.addWidget(QLabel("Speed limit per file (KB/s, 0 = unlimited):"), 2, 0)
        self.speed_limit = QSpinBox()
        self.speed_limit.setRange(0, 10_000_000)
        self.speed_limit.setValue(0)
        settings_grid.addWidget(self.speed_limit, 2, 1)
        settings_grid.addWidget(QLabel("Torrent upload limit (KB/s, 0 = unlimited):"), 3, 0)
        self.torrent_upload_limit = QSpinBox()
        self.torrent_upload_limit.setRange(0, 10_000_000)
        self.torrent_upload_limit.setValue(1)
        self.torrent_upload_limit.setToolTip("Maximum upload rate while seeding torrents")
        self.torrent_upload_limit.valueChanged.connect(self.update_torrent_upload_limit)
        settings_grid.addWidget(self.torrent_upload_limit, 3, 1)
        self.proxy_enabled = QCheckBox("Use HTTP/HTTPS proxy")
        settings_grid.addWidget(self.proxy_enabled, 4, 0, 1, 2)
        self.proxy_url = QLineEdit()
        self.proxy_url.setPlaceholderText("http://127.0.0.1:8080")
        settings_grid.addWidget(self.proxy_url, 5, 0, 1, 2)
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
        downloads_layout.addWidget(self.table, 1)
        self.table.cellDoubleClicked.connect(self.open_or_show_download)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        schedule_page = QWidget()
        schedule_layout = QVBoxLayout(schedule_page)
        schedule_layout.setContentsMargins(10, 10, 10, 10)
        schedule_layout.addWidget(QLabel("Select a queued file, choose its start date and time, then apply the schedule."))

        self.schedule_table = QTableWidget(0, 3)
        self.schedule_table.setHorizontalHeaderLabels(["File", "Status", "Scheduled start"])
        self.schedule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.schedule_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.schedule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.schedule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.schedule_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.schedule_table.itemSelectionChanged.connect(self.load_selected_schedule)
        schedule_layout.addWidget(self.schedule_table, 1)

        schedule_controls = QHBoxLayout()
        schedule_controls.addWidget(QLabel("Start date and time:"))
        self.schedule_editor = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.schedule_editor.setCalendarPopup(True)
        self.schedule_editor.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.schedule_editor.setMinimumWidth(175)
        schedule_controls.addWidget(self.schedule_editor)
        apply_schedule = QPushButton("Apply to selected file")
        apply_schedule.clicked.connect(self.apply_selected_schedule)
        schedule_controls.addWidget(apply_schedule)
        clear_schedule = QPushButton("Clear schedule")
        clear_schedule.clicked.connect(self.clear_selected_schedule)
        schedule_controls.addWidget(clear_schedule)
        start_now = QPushButton("Start now")
        start_now.clicked.connect(self.start_selected_now)
        schedule_controls.addWidget(start_now)
        schedule_controls.addStretch(1)
        schedule_layout.addLayout(schedule_controls)

        link_controls = QHBoxLayout()
        link_controls.addWidget(QLabel("Download URL:"))
        self.schedule_url = QLineEdit()
        self.schedule_url.setPlaceholderText("Paste a direct HTTP or HTTPS download link")
        self.schedule_url.returnPressed.connect(self.add_scheduled_link)
        link_controls.addWidget(self.schedule_url, 1)
        add_link = QPushButton("Add link to schedule")
        add_link.clicked.connect(self.add_scheduled_link)
        link_controls.addWidget(add_link)
        schedule_layout.addLayout(link_controls)

        self.schedule_hint = QLabel("Choose a start date/time, paste a direct link, then click Add link to schedule.")
        schedule_layout.addWidget(self.schedule_hint)
        self.tabs.addTab(schedule_page, "Schedule")
        self.website_page = WebsiteDownloaderDialog(self)
        self.tabs.addTab(self.website_page, "Website scan")
        self.tabs.currentChanged.connect(
            lambda index: self.refresh_schedule_table() if index == 1 else None
        )


        # Smart Link Grabber: inspect a page and let the user choose candidate files.
        grabber_page = QWidget()
        grabber_layout = QVBoxLayout(grabber_page)
        grabber_layout.setContentsMargins(10, 10, 10, 10)
        grabber_layout.addWidget(QLabel(f"Enter a webpage URL. {APP_NAME} will find common downloadable file links; review the list before queueing."))
        grabber_url_row = QHBoxLayout()
        self.grabber_url = QLineEdit()
        self.grabber_url.setPlaceholderText("https://example.com/downloads")
        self.grabber_url.returnPressed.connect(self.start_link_grab)
        grabber_url_row.addWidget(self.grabber_url, 1)
        self.grabber_scan_button = QPushButton("Scan page")
        self.grabber_scan_button.clicked.connect(self.start_link_grab)
        grabber_url_row.addWidget(self.grabber_scan_button)
        grabber_layout.addLayout(grabber_url_row)
        self.grabber_table = QTableWidget(0, 2)
        self.grabber_table.setHorizontalHeaderLabels(["File name", "Download URL"])
        self.grabber_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.grabber_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grabber_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grabber_table.verticalHeader().setVisible(False)
        self.grabber_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.grabber_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        grabber_layout.addWidget(self.grabber_table, 1)
        grabber_actions = QHBoxLayout()
        self.grabber_select_all = QPushButton("Select all")
        self.grabber_select_all.clicked.connect(self.grabber_table.selectAll)
        grabber_actions.addWidget(self.grabber_select_all)
        self.grabber_queue_button = QPushButton("Queue selected links")
        self.grabber_queue_button.clicked.connect(self.queue_grabber_selected)
        grabber_actions.addWidget(self.grabber_queue_button)
        grabber_actions.addStretch(1)
        grabber_layout.addLayout(grabber_actions)
        self.grabber_status = QLabel("No page scanned yet.")
        grabber_layout.addWidget(self.grabber_status)
        self.tabs.addTab(grabber_page, "Smart Grabber")

        # Download Analytics: live summary based on the existing task/history records.
        analytics_page = QWidget()
        analytics_layout = QVBoxLayout(analytics_page)
        analytics_layout.setContentsMargins(12, 12, 12, 12)
        analytics_layout.addWidget(QLabel("Your download activity at a glance"))
        analytics_cards = QGridLayout()
        self.analytics_total = QLabel("0")
        self.analytics_completed = QLabel("0")
        self.analytics_active = QLabel("0")
        self.analytics_volume = QLabel("0 B")
        for col, (caption_text, value_label) in enumerate((
            ("TOTAL TASKS", self.analytics_total),
            ("COMPLETED", self.analytics_completed),
            ("ACTIVE / QUEUED", self.analytics_active),
            ("COMPLETED DATA", self.analytics_volume)
        )):
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            card_layout = QVBoxLayout(card)
            caption = QLabel(caption_text)
            caption.setStyleSheet("color:#888;font-size:9pt;font-weight:700;")
            value_label.setStyleSheet("font-size:20pt;font-weight:700;")
            card_layout.addWidget(caption)
            card_layout.addWidget(value_label)
            analytics_cards.addWidget(card, 0, col)
        analytics_layout.addLayout(analytics_cards)
        self.analytics_speed = QLabel("Live speed history: waiting for download activity")
        self.analytics_speed.setMinimumHeight(36)
        self.analytics_speed.setStyleSheet("font-family: Consolas, monospace; font-size: 11pt; padding: 6px;")
        analytics_layout.addWidget(self.analytics_speed)
        analytics_layout.addWidget(QLabel("Downloads by file category"))
        self.analytics_table = QTableWidget(0, 2)
        self.analytics_table.setHorizontalHeaderLabels(["Category", "Files"])
        self.analytics_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.analytics_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.analytics_table.verticalHeader().setVisible(False)
        self.analytics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        analytics_layout.addWidget(self.analytics_table, 1)
        analytics_refresh = QPushButton("Refresh statistics")
        analytics_refresh.clicked.connect(self.refresh_analytics)
        analytics_layout.addWidget(analytics_refresh)
        export_row = QHBoxLayout()
        self.analytics_format = QComboBox()
        self.analytics_format.addItem("CSV", "csv")
        self.analytics_format.addItem("JSON", "json")
        export_row.addWidget(self.analytics_format)
        export_button = QPushButton("Export report…")
        export_button.clicked.connect(self.export_analytics_report)
        export_row.addWidget(export_button)
        export_row.addStretch(1)
        analytics_layout.addLayout(export_row)
        self.tabs.addTab(analytics_page, "Analytics")

        # Select the visual preset automatically for the current desktop OS.
        # No theme-selection tab is exposed in the product UI.
        self.theme_combo = QComboBox()
        if sys.platform.startswith("linux"):
            self.theme_combo.addItem("Ubuntu Yaru", "ubuntu_yaru")
        else:
            self.theme_combo.addItem("Windows 11 Fluent", "fluent")
        self.theme_preview = QLabel()

        self.status = QLabel("Ready — add a URL to begin.")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.status)
        self.refresh_schedule_table()
        self.refresh_analytics()


    def add_scheduled_link(self):
        """Create a queued HTTP(S) task directly from the Schedule tab."""
        url = self.schedule_url.text().strip()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(
                self, "Invalid download link",
                "Enter a valid direct HTTP or HTTPS download URL."
            )
            return

        selected_time = self.schedule_editor.dateTime()
        if selected_time <= QDateTime.currentDateTime():
            QMessageBox.warning(self, "Invalid time", "Choose a future date and time before adding the link.")
            return

        folder = self.folder.text().strip()
        if not folder:
            QMessageBox.warning(self, "Folder required", "Choose a download folder in the Downloads tab first.")
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Folder error", str(exc))
            return

        name = os.path.basename(urllib.parse.unquote(parsed.path)) or "Download"
        task_id = uuid.uuid4().hex
        self.tasks[task_id] = {
            "id": task_id, "url": normalized_url, "folder": folder, "name": name,
            "status": "Queued", "downloaded": 0, "total": 0,
            "speed": 0.0, "eta": -1.0, "path": "",
            "worker": None, "history": False, "scheduled_at": selected_time.toString(Qt.ISODate),
            "category": category_for_filename(name),
            "post_action_enabled": False, "post_action": "none", "post_action_done": False
        }
        self.save_tasks()
        self.schedule_url.clear()
        self.refresh_table()
        self.refresh_schedule_table()
        self.status.setText(
            f"Added {name} to the schedule for {selected_time.toString('yyyy-MM-dd HH:mm')}."
        )

    def refresh_schedule_table(self):
        if not hasattr(self, "schedule_table"):
            return
        selected_id = self.selected_schedule_task()
        entries = list(self.tasks.items())
        self.schedule_table.setRowCount(len(entries))
        selected_row = -1
        for row, (task_id, task) in enumerate(entries):
            name_item = QTableWidgetItem(task.get("name", "Download"))
            name_item.setData(Qt.UserRole, task_id)
            status_item = QTableWidgetItem(task.get("status", "Unknown"))
            scheduled_at = task.get("scheduled_at", "")
            if scheduled_at:
                try:
                    scheduled_text = datetime.datetime.fromisoformat(scheduled_at).astimezone().strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    scheduled_text = scheduled_at
            else:
                scheduled_text = "Not scheduled"
            time_item = QTableWidgetItem(scheduled_text)
            self.schedule_table.setItem(row, 0, name_item)
            self.schedule_table.setItem(row, 1, status_item)
            self.schedule_table.setItem(row, 2, time_item)
            if task_id == selected_id:
                selected_row = row
        if selected_row >= 0:
            self.schedule_table.selectRow(selected_row)
        elif entries and self.schedule_table.currentRow() < 0:
            self.schedule_table.selectRow(0)

    def selected_schedule_task(self):
        if not hasattr(self, "schedule_table"):
            return None
        row = self.schedule_table.currentRow()
        item = self.schedule_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def load_selected_schedule(self):
        task_id = self.selected_schedule_task()
        task = self.tasks.get(task_id) if task_id else None
        if not task:
            return
        scheduled_at = task.get("scheduled_at", "")
        if scheduled_at:
            try:
                scheduled = datetime.datetime.fromisoformat(scheduled_at).astimezone()
                self.schedule_editor.setDateTime(QDateTime.fromSecsSinceEpoch(int(scheduled.timestamp())))
            except (ValueError, TypeError, OverflowError):
                self.schedule_editor.setDateTime(QDateTime.currentDateTime().addSecs(300))
        else:
            self.schedule_editor.setDateTime(QDateTime.currentDateTime().addSecs(300))
        self.schedule_hint.setText(f"Selected: {task.get('name', 'Download')} — schedule is stored separately for this file.")

    def apply_selected_schedule(self):
        task_id = self.selected_schedule_task()
        task = self.tasks.get(task_id) if task_id else None
        if not task:
            QMessageBox.information(self, "Select a file", "Select a file in the Schedule tab first.")
            return
        if task.get("status") != "Queued":
            QMessageBox.information(self, "Cannot schedule", "Only queued downloads can be scheduled. Pause or queue the file first.")
            return
        selected_time = self.schedule_editor.dateTime()
        if selected_time <= QDateTime.currentDateTime():
            QMessageBox.warning(self, "Invalid time", "Choose a future date and time.")
            return
        task["scheduled_at"] = selected_time.toString(Qt.ISODate)
        self.save_tasks()
        self.refresh_schedule_table()
        self.status.setText(f"Scheduled {task.get('name', 'download')} for {selected_time.toString('yyyy-MM-dd HH:mm')}.")

    def clear_selected_schedule(self):
        task_id = self.selected_schedule_task()
        task = self.tasks.get(task_id) if task_id else None
        if not task:
            QMessageBox.information(self, "Select a file", "Select a file in the Schedule tab first.")
            return
        task["scheduled_at"] = ""
        self.save_tasks()
        self.refresh_schedule_table()
        self.status.setText(f"Schedule cleared for {task.get('name', 'download')}.")

    def start_selected_now(self):
        task_id = self.selected_schedule_task()
        task = self.tasks.get(task_id) if task_id else None
        if not task:
            QMessageBox.information(self, "Select a file", "Select a file in the Schedule tab first.")
            return
        if task.get("status") != "Queued":
            QMessageBox.information(self, "Not queued", "Only queued downloads can be started from this tab.")
            return
        task["scheduled_at"] = ""
        self.save_tasks()
        self.schedule_downloads()
        self.refresh_schedule_table()


    def start_link_grab(self):
        # Accept bare domains and normalize HTTP/HTTPS exactly like Website Scan.
        page_url = WebsiteScanWorker.prepare_url(self.grabber_url.text().strip())
        if not page_url:
            QMessageBox.warning(self, "Smart Link Grabber", "Enter a valid HTTP or HTTPS webpage URL.")
            return
        self.grabber_url.setText(page_url)
        if self.grabber_worker and self.grabber_worker.isRunning():
            return
        self.grabber_scan_button.setEnabled(False)
        self.grabber_status.setText("Scanning page for downloadable links…")
        self.grabber_table.setRowCount(0)
        self.grabber_worker = LinkGrabberWorker(page_url)
        self.grabber_worker.results_ready.connect(self.on_grabber_results)
        self.grabber_worker.failed.connect(self.on_grabber_failed)
        self.grabber_worker.start()

    def on_grabber_results(self, results):
        self.grabber_results = list(results)
        self.grabber_table.setRowCount(len(results))
        for row, (url, name) in enumerate(results):
            self.grabber_table.setItem(row, 0, QTableWidgetItem(name))
            self.grabber_table.setItem(row, 1, QTableWidgetItem(url))
        self.grabber_scan_button.setEnabled(True)
        self.grabber_status.setText(
            f"Found {len(results)} candidate file link(s). Select the files you want to queue."
            if results else "No common downloadable file links were found on this page."
        )

    def on_grabber_failed(self, message):
        self.grabber_scan_button.setEnabled(True)
        self.grabber_status.setText("Scan failed: " + message)

    def queue_grabber_selected(self):
        rows = sorted({index.row() for index in self.grabber_table.selectionModel().selectedRows()})
        if not rows:
            QMessageBox.information(self, "Smart Link Grabber", "Select one or more links first.")
            return
        selected = [self.grabber_results[row] for row in rows if row < len(self.grabber_results)]
        folder = self.folder.text().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        added = self.add_website_downloads(selected, folder)
        self.status.setText(f"Smart Grabber queued {added} selected file(s).")
        self.tabs.setCurrentIndex(0)

    def on_clipboard_changed(self):
        if not hasattr(self, "clipboard_monitor") or not self.clipboard_monitor.isChecked():
            return
        value = QApplication.clipboard().text().strip()
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.netloc and value != self.url.text().strip():
            self.url.setText(value)
            self.status.setText("Clipboard Monitor detected a web link and placed it in the URL field. Press Start Download when ready.")

    def apply_native_glass_backdrop(self, enabled):
        """Enable a real OS-level blurred desktop backdrop for the Crystal Aqua theme."""
        if sys.platform != "win32":
            if hasattr(self, "setAttribute"):
                self.setAttribute(Qt.WA_TranslucentBackground, False)
            return

        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            if enabled:
                # Required for the DWM material to be visible through the Qt window.
                self.setAttribute(Qt.WA_TranslucentBackground, True)
                self.setAttribute(Qt.WA_NoSystemBackground, True)
                hwnd = int(self.winId())

                # Windows 11 22H2+: use the native Transient Window (acrylic)
                # system backdrop, which blurs the actual desktop behind the app.
                dwm = ctypes.WinDLL("dwmapi")
                attribute = 38  # DWMWA_SYSTEMBACKDROP_TYPE
                backdrop_type = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW
                result = dwm.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd), attribute,
                    ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type)
                )
                if result == 0:
                    return

                # Windows 10 fallback: legacy Acrylic blur-behind composition.
                class ACCENT_POLICY(ctypes.Structure):
                    _fields_ = [
                        ("AccentState", ctypes.c_int),
                        ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint),
                        ("AnimationId", ctypes.c_int),
                    ]

                class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                    _fields_ = [
                        ("Attribute", ctypes.c_int),
                        ("Data", ctypes.c_void_p),
                        ("SizeOfData", ctypes.c_size_t),
                    ]

                user32 = ctypes.WinDLL("user32", use_last_error=True)
                set_composition = user32.SetWindowCompositionAttribute
                set_composition.argtypes = [
                    wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)
                ]
                set_composition.restype = wintypes.BOOL
                policy = ACCENT_POLICY(4, 2, 0xCCBFE9EF, 0)  # Acrylic blur, aqua tint
                data = WINDOWCOMPOSITIONATTRIBDATA(
                    19, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
                    ctypes.sizeof(policy)
                )
                set_composition(wintypes.HWND(hwnd), ctypes.byref(data))
            else:
                # Remove native blur when switching back to a non-glass theme.
                try:
                    dwm = ctypes.WinDLL("dwmapi")
                    backdrop_type = ctypes.c_int(1)  # DWMSBT_NONE
                    dwm.DwmSetWindowAttribute(
                        wintypes.HWND(hwnd), 38,
                        ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type)
                    )
                except Exception:
                    pass
                self.setAttribute(Qt.WA_NoSystemBackground, False)
                self.setAttribute(Qt.WA_TranslucentBackground, False)
        except Exception:
            # Keep theme switching safe on unsupported Windows builds and systems.
            try:
                self.setAttribute(Qt.WA_NoSystemBackground, False)
                self.setAttribute(Qt.WA_TranslucentBackground, False)
            except Exception:
                pass

    def apply_selected_theme(self):
        theme = self.theme_combo.currentData()
        palettes = {
            "dark": ("#171a21", "#202631", "#293241", "#e8edf5", "#aab6c8", "#e34b5b", "#ffffff", "#343e4e"),
            "ubuntu": ("#2c001e", "#3d1834", "#51263f", "#fff4fb", "#d9b9ce", "#e95420", "#ffffff", "#772953"),
            "light": ("#f3f6fb", "#ffffff", "#e9eef6", "#202938", "#65738a", "#2878d0", "#ffffff", "#d5e0ee"),
            "blue": ("#0e1a2b", "#14263c", "#1c3550", "#e8f2ff", "#9fb8d2", "#2997e8", "#ffffff", "#294d70"),
            "oled": ("#000000", "#101114", "#1a1b20", "#f5f5f7", "#a6a8b0", "#8b5cf6", "#ffffff", "#30313a"),
            "nord": ("#2e3440", "#3b4252", "#434c5e", "#eceff4", "#c0c8d8", "#88c0d0", "#20242b", "#5e81ac"),
            "dracula": ("#282a36", "#343746", "#44475a", "#f8f8f2", "#bdc0d0", "#bd93f9", "#282a36", "#6272a4"),
            "cyber": ("#0b1020", "#111a30", "#1b2945", "#e6f7ff", "#8ba6c9", "#00e5ff", "#07111d", "#31516f"),
            "sonoma": ("#20232b", "#292e38", "#343b48", "#f5f6fa", "#b6bfce", "#8b9cff", "#ffffff", "#4a5262"),
            "fluent": ("#f3f5f9", "#ffffff", "#e8edf5", "#1d2635", "#66758b", "#536fcb", "#ffffff", "#d5ddeb"),
            "ubuntu_yaru": ("#f6f5f4", "#ffffff", "#e8e6e3", "#241f31", "#5e5c64", "#e95420", "#ffffff", "#d5d3cf"),
            "solarized": ("#002b36", "#073642", "#164752", "#eee8d5", "#93a1a1", "#2aa198", "#002b36", "#586e75"),
            "rose": ("#191724", "#26233a", "#393552", "#e0def4", "#908caa", "#eb6f92", "#191724", "#6e6a86"),
            "aero_blue": ("#d9efff", "#eaf7ff", "#ffffff", "#18364f", "#54738b", "#269fe8", "#ffffff", "#a9d8f4"),
            "aero_light": ("#e9f4fa", "#f8fcff", "#ffffff", "#263d4d", "#688294", "#4b9fc8", "#ffffff", "#c2dce9"),
            "crystal": ("#eef2f7", "#ffffff", "#f9fcff", "#263344", "#718096", "#6b9ed8", "#ffffff", "#d2deeb"),
            "aero_sunset": ("#fff0ed", "#fff8f5", "#ffffff", "#54384a", "#927286", "#d77ca7", "#ffffff", "#f0c7d8"),
            "aero_dark": ("#172638", "#20364c", "#2b4962", "#eff8ff", "#b5d0e2", "#58c4f5", "#10283a", "#527b98"),
            "aero_kubuntu": ("#e6eaff", "#f5f6ff", "#ffffff", "#242b50", "#66709a", "#3b5ccc", "#ffffff", "#c4ccef"),
            "aero_ubuntu": ("#fff0e8", "#fff8f4", "#ffffff", "#4a2635", "#916b78", "#e95420", "#ffffff", "#f1c5b4"),
            "aero_windows11": ("#e8f3ff", "#f5faff", "#ffffff", "#1d3554", "#617d9c", "#0878d4", "#ffffff", "#b8d7f2"),
            "emerald_glass": ("#e1f5e9", "#f3fff7", "#ffffff", "#174832", "#5d8870", "#19a568", "#ffffff", "#a8dfbf"),
            "aurora_spectrum": ("#f0eaff", "#fff8ff", "#ffffff", "#382c58", "#78668e", "#8757d6", "#ffffff", "#d9c4f2"),
            "crystal_aqua_glass": ("#dff7f7", "#f4ffff", "#ffffff", "#173d4a", "#5b8290", "#16a879", "#ffffff", "#a9dfe3")
        }
        bg, panel, raised, fg, muted, accent, accent_text, border = palettes.get(theme, palettes["dark"])
        is_light = theme in ("light", "fluent", "aero_blue", "aero_light", "crystal", "aero_sunset",
                             "aero_kubuntu", "aero_ubuntu", "aero_windows11", "ubuntu_yaru",
                             "emerald_glass", "aurora_spectrum", "crystal_aqua_glass")
        selection = accent
        self._active_theme_palette = {
            "background": bg, "panel": panel, "raised": raised,
            "foreground": fg, "muted": muted, "accent": accent, "border": border
        }
        font_family = '"Ubuntu", "Cantarell", "Noto Sans", sans-serif' if theme == "ubuntu_yaru" else '"Segoe UI", "Inter", "Noto Sans", sans-serif'
        qss = f"""
            QWidget {{
                background-color: {bg}; color: {fg};
                font-family: {font_family};
                font-size: 10pt;
            }}
            QMainWindow, QDialog {{ background-color: {bg}; }}
            QTabWidget::pane {{
                border: 1px solid {border}; border-radius: 10px;
                top: -1px; background: {panel};
            }}
            QTabBar::tab {{
                background: {raised}; color: {muted}; border: 1px solid {border};
                padding: 9px 17px; margin-right: 4px;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
            }}
            QTabBar::tab:selected {{
                background: {panel}; color: {accent};
                border-bottom: 3px solid {accent}; font-weight: 700;
            }}
            QTabBar::tab:hover:!selected {{ color: {fg}; background: {panel}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QDateEdit,
            QTimeEdit, QComboBox, QTextEdit, QPlainTextEdit, QTableWidget,
            QTableView, QListWidget, QTreeWidget, QTreeView {{
                background: {panel}; color: {fg}; border: 1px solid {border};
                border-radius: 7px; padding: 6px; selection-background-color: {selection};
                selection-color: {accent_text};
            }}
            QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus, QComboBox:focus,
            QTextEdit:focus, QPlainTextEdit:focus {{
                border: 2px solid {accent};
            }}
            QComboBox::drop-down {{ border: 0; width: 25px; }}
            QComboBox QAbstractItemView {{
                background: {panel}; color: {fg}; border: 1px solid {border};
                selection-background-color: {accent}; selection-color: {accent_text};
            }}
            QPushButton {{
                background: {raised}; color: {fg}; border: 1px solid {border};
                border-radius: 8px; padding: 8px 15px; min-height: 20px;
            }}
            QPushButton:enabled {{ color: #1d2635; background: {raised}; border: 1px solid #aebbd0; font-weight: 600; }}
            QPushButton:hover:enabled {{ background: {accent}; color: {accent_text}; border-color: {accent}; }}
            QPushButton:pressed:enabled {{ background: {border}; }}
            QPushButton:disabled {{ color: #778397; background: #e5e9f0; border: 1px dashed #aab4c2; font-weight: 400; }}
            QHeaderView::section {{
                background: {raised}; color: {fg}; border: 0;
                border-bottom: 1px solid {border}; padding: 8px; font-weight: 700;
            }}
            QTableWidget {{ gridline-color: {border}; alternate-background-color: {raised}; }}
            QTableWidget::item {{ padding: 5px; }}
            QProgressBar {{
                background: {raised}; color: {fg}; border: 1px solid {border};
                border-radius: 6px; text-align: center; min-height: 13px;
            }}
            QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
            QCheckBox, QRadioButton {{ spacing: 8px; }}
            QCheckBox::indicator, QRadioButton::indicator {{
                width: 16px; height: 16px;
            }}
            QGroupBox {{
                border: 1px solid {border}; border-radius: 9px;
                margin-top: 12px; padding: 12px 8px 8px; font-weight: 700;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {accent}; }}
            QMenuBar {{ background: {panel}; color: {fg}; border-bottom: 1px solid {border}; }}
            QMenuBar::item:selected, QMenu::item:selected {{ background: {accent}; color: {accent_text}; }}
            QMenu {{ background: {panel}; color: {fg}; border: 1px solid {border}; padding: 5px; }}
            QStatusBar {{ background: {panel}; color: {muted}; border-top: 1px solid {border}; }}
            QToolTip {{ background: {raised}; color: {fg}; border: 1px solid {accent}; padding: 5px; }}
            QScrollBar:vertical {{ background: {bg}; width: 12px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {border}; min-height: 25px; border-radius: 5px; }}
            QScrollBar::handle:vertical:hover {{ background: {accent}; }}
            QScrollBar:horizontal {{ background: {bg}; height: 12px; margin: 2px; }}
            QScrollBar::handle:horizontal {{ background: {border}; min-width: 25px; border-radius: 5px; }}
            QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
            QToolButton {{ background: {raised}; color: {fg}; border: 1px solid {border}; border-radius: 7px; padding: 6px; }}
            QToolButton:hover {{ background: {accent}; color: {accent_text}; }}
        """
        # Aero Glass presets use layered gradients, translucent-looking surfaces,
        # bright inner highlights and bevel-like borders. Qt stylesheets do not
        # provide true desktop backdrop blur; this is a lightweight glass visual.
        glass_qss = ""
        native_glass = (theme == "crystal_aqua_glass")
        self.apply_native_glass_backdrop(native_glass)
        if theme.startswith("aero_") or theme in ("crystal", "emerald_glass", "aurora_spectrum", "crystal_aqua_glass"):
            if theme == "aero_blue":
                base_a, base_b = "#cceaff", "#f4fbff"
                surface_a, surface_b = "rgba(255,255,255,0.88)", "rgba(220,242,255,0.78)"
                edge, glow = "#ffffff", "#65bff0"
            elif theme == "aero_light":
                base_a, base_b = "#dcecf5", "#f9fdff"
                surface_a, surface_b = "rgba(255,255,255,0.92)", "rgba(230,244,250,0.82)"
                edge, glow = "#ffffff", "#8bc7e2"
            elif theme == "crystal":
                base_a, base_b = "#e2eaf3", "#ffffff"
                surface_a, surface_b = "rgba(255,255,255,0.96)", "rgba(238,245,252,0.88)"
                edge, glow = "#ffffff", "#9bbce0"
            elif theme == "aero_sunset":
                base_a, base_b = "#f8dce8", "#fff8f2"
                surface_a, surface_b = "rgba(255,255,255,0.92)", "rgba(255,232,239,0.82)"
                edge, glow = "#ffffff", "#e6a0bd"
            elif theme == "aero_kubuntu":
                base_a, base_b = "#d9e0ff", "#f7f8ff"
                surface_a, surface_b = "rgba(255,255,255,0.94)", "rgba(222,228,255,0.82)"
                edge, glow = "#ffffff", "#697fe0"
            elif theme == "aero_ubuntu":
                base_a, base_b = "#f8d9ca", "#fff8f2"
                surface_a, surface_b = "rgba(255,255,255,0.94)", "rgba(255,228,215,0.82)"
                edge, glow = "#ffffff", "#e95420"
            elif theme == "aero_windows11":
                base_a, base_b = "#cfe7ff", "#f5fbff"
                surface_a, surface_b = "rgba(255,255,255,0.94)", "rgba(220,239,255,0.82)"
                edge, glow = "#ffffff", "#1685dc"
            elif theme == "emerald_glass":
                base_a, base_b = "#c9efd9", "#f4fff8"
                surface_a, surface_b = "rgba(255,255,255,0.94)", "rgba(214,246,226,0.82)"
                edge, glow = "#ffffff", "#20a66a"
            elif theme == "aurora_spectrum":
                base_a, base_b = "#e5d8ff", "#fff0f8"
                surface_a, surface_b = "rgba(255,255,255,0.94)", "rgba(241,225,255,0.82)"
                edge, glow = "#ffffff", "#a05ce0"
            elif theme == "crystal_aqua_glass":
                # Translucent aqua-glass surfaces with a visible layered backdrop.
                base_a, base_b = "#bfe9ef", "#eaffff"
                surface_a, surface_b = "rgba(255,255,255,0.66)", "rgba(202,242,240,0.48)"
                edge, glow = "#ffffff", "#18a9b8"
            else:
                base_a, base_b = "#102338", "#294a65"
                surface_a, surface_b = "rgba(91,133,164,0.42)", "rgba(25,49,70,0.88)"
                edge, glow = "#9bdcff", "#45bdf5"
            glass_backdrop = (
                "qlineargradient(x1:0,y1:0,x2:1,y2:1, "
                "stop:0 rgba(183,232,239,0.74), "
                "stop:0.52 rgba(231,251,252,0.58), "
                "stop:1 rgba(177,225,231,0.68))"
                if theme == "crystal_aqua_glass"
                else f"qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {base_a}, stop:1 {base_b})"
            )
            glass_qss = f"""
                QWidget {{ background: {glass_backdrop}; }}
                QMainWindow, QDialog {{ border: 1px solid {edge}; }}
                QTabWidget::pane, QGroupBox {{
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {surface_a}, stop:1 {surface_b});
                    border: 1px solid {edge}; border-top: 2px solid #ffffff;
                    border-radius: 13px;
                }}
                QTabWidget, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
                    background: transparent; border: 0;
                }}
                QLineEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QComboBox,
                QTextEdit, QTableWidget, QListWidget {{
                    background: {surface_a}; border: 1px solid {edge};
                    border-top-color: #ffffff; border-radius: 10px;
                }}
                QPushButton, QToolButton {{
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #ffffff, stop:0.48 {surface_a}, stop:1 {surface_b});
                    border: 1px solid {edge}; border-top: 2px solid #ffffff;
                    border-bottom: 2px solid {glow}; border-radius: 11px;
                    padding: 8px 16px; font-weight: 600;
                }}
                QPushButton:hover, QToolButton:hover {{
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #ffffff, stop:1 {glow});
                    border: 1px solid {glow};
                }}
                QPushButton:pressed, QToolButton:pressed {{
                    background: {surface_b}; border-top: 2px solid {glow};
                    border-bottom: 1px solid {edge}; padding-top: 9px;
                }}
                QTabBar::tab {{
                    background: {surface_b}; border: 1px solid {edge};
                    border-radius: 9px; padding: 9px 16px; margin: 3px;
                }}
                QTabBar::tab:selected {{
                    background: {surface_a}; border: 2px solid {glow};
                    color: {accent}; font-weight: 700;
                }}
                QHeaderView::section {{
                    background: {surface_b}; border: 0;
                    border-bottom: 1px solid {edge}; padding: 8px;
                }}
                QProgressBar {{
                    background: {surface_b}; border: 1px solid {edge};
                    border-radius: 8px; text-align: center;
                }}
                QProgressBar::chunk {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {accent}, stop:1 {glow}); border-radius: 7px;
                }}
            """
            if native_glass:
                # Let the real DWM acrylic material show through the entire top-level
                # window. Interactive controls retain their own translucent surfaces.
                glass_qss += f"""
                    QWidget {{ background: transparent; }}
                    QMainWindow, QDialog {{ background: transparent; }}
                    QTabWidget::pane, QGroupBox {{
                        background: rgba(225,250,250,0.34);
                        border: 1px solid rgba(255,255,255,0.82);
                    }}
                    QLineEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QComboBox,
                    QTextEdit, QTableWidget, QListWidget {{
                        background: rgba(245,255,255,0.42);
                        border: 1px solid rgba(255,255,255,0.78);
                    }}
                    QPushButton, QToolButton {{
                        background: rgba(255,255,255,0.48);
                        border: 1px solid rgba(255,255,255,0.9);
                    }}
                    QHeaderView::section {{
                        background: rgba(205,241,242,0.48);
                    }}
                    QMenuBar, QMenu, QStatusBar {{
                        background: rgba(225,250,250,0.38);
                    }}
                    QTableWidget::item {{ background: transparent; }}
                """
        app = QApplication.instance()
        if app:
            app.setStyle("Fusion")
            app.setStyleSheet(qss + glass_qss)
        if hasattr(self, "settings"):
            self.settings.setValue("theme", theme)
            self.settings.sync()
        if hasattr(self, "theme_preview"):
            self.theme_preview.setText(
                f"●  {self.theme_combo.currentText()}    Accent: {accent}    "
                "Theme applied to the entire GNS Downloader interface"
            )
            preview_background = (
                f"qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {panel}, stop:1 {raised})"
                if theme.startswith("aero_") or theme in ("crystal", "emerald_glass", "aurora_spectrum", "crystal_aqua_glass") else panel
            )
            self.theme_preview.setStyleSheet(
                f"background:{preview_background}; color:{fg}; border:2px solid {accent}; "
                "border-top:2px solid white; border-radius:16px; padding:22px; "
                "font-size:12pt; font-weight:600;"
            )

    def export_analytics_report(self):
        path, selected = QFileDialog.getSaveFileName(self, "Export download report", "GNS-Downloader-report.csv", "CSV files (*.csv);;JSON files (*.json)")
        if not path:
            return
        fields = ("name", "url", "status", "category", "downloaded", "total", "speed", "eta", "path", "folder", "content_type")
        rows = [{key: task.get(key, "") for key in fields} for task in self.tasks.values()]
        try:
            use_json = path.lower().endswith(".json") or "JSON" in selected
            if use_json:
                if not path.lower().endswith(".json"): path += ".json"
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(rows, handle, ensure_ascii=False, indent=2)
            else:
                if not path.lower().endswith(".csv"): path += ".csv"
                with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            self.status.setText("Report exported: " + path)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def refresh_analytics(self):
        if not hasattr(self, "analytics_table"):
            return
        tasks = list(self.tasks.values())
        total = len(tasks)
        completed = sum(1 for task in tasks if task.get("status") == "Completed")
        active_queued = sum(1 for task in tasks if task.get("status") in (
            "Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding", "Queued", "Ready"
        ))
        volume = sum(
            int(task.get("downloaded") or 0) for task in tasks
            if task.get("status") == "Completed"
        )
        self.analytics_total.setText(str(total))
        self.analytics_completed.setText(str(completed))
        self.analytics_active.setText(str(active_queued))
        self.analytics_volume.setText(format_bytes(volume))
        samples = [max(0.0, value) for _, value in self._speed_samples[-36:]]
        if samples:
            peak = max(samples)
            bars = "▁▂▃▄▅▆▇█"
            spark = "".join(bars[min(7, int((value / peak) * 7))] if peak else "▁" for value in samples)
            self.analytics_speed.setText(f"Recent speed  {spark}    Peak: {format_bytes(peak)}/s")
        counts = {}
        for task in tasks:
            category = task.get("category") or category_for_filename(task.get("name", ""))
            counts[category] = counts.get(category, 0) + 1
        self.analytics_table.setRowCount(len(counts))
        for row, (category, count) in enumerate(sorted(counts.items(), key=lambda item: (-item[1], item[0]))):
            self.analytics_table.setItem(row, 0, QTableWidgetItem(category))
            self.analytics_table.setItem(row, 1, QTableWidgetItem(str(count)))

    def open_settings_dialog(self):
        self.settings_dialog.exec()

    def save_and_close_settings(self):
        self.save_preferences()
        self.settings_dialog.accept()

    def show_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Created by MeysamGNS\n"
            "Developed with assistance from ChatGPT\n\n"
            "A lightweight download manager with configurable multi-part downloads (up to 16 connections), pause and resume, speed limits, and download queue management."
        )

    def check_for_updates(self):
        worker = getattr(self, "_update_worker", None)
        download_worker = getattr(self, "_update_download_worker", None)
        if ((worker is not None and worker.isRunning())
                or (download_worker is not None and download_worker.isRunning())):
            QMessageBox.information(self, "Updates", "An update operation is already running.")
            return
        self.status.setText("Checking GitHub for updates…")
        worker = GitHubUpdateWorker(APP_VERSION)
        self._update_worker = worker
        worker.update_available.connect(self.on_update_available)
        worker.up_to_date.connect(self.on_update_up_to_date)
        worker.failed.connect(self.on_update_check_failed)
        worker.start()

    def on_update_up_to_date(self, version):
        self.status.setText(f"You are using the latest version ({APP_VERSION}).")
        QMessageBox.information(self, "No updates available", f"GNS Downloader {APP_VERSION} is up to date.")

    def on_update_check_failed(self, message):
        self.status.setText("GitHub update check failed.")
        QMessageBox.warning(self, "Update check failed", f"Could not check GitHub for updates:\n{message}")

    def on_update_available(self, version, notes, release_url, asset_url, asset_size, asset_digest):
        summary = (
            f"GNS Downloader {version} is available.\n"
            f"Current version: {APP_VERSION}\n\n"
            "Release notes:\n"
            + (notes[:12000] if notes else "No release notes were provided.")
        )
        if not asset_url:
            answer = QMessageBox.question(
                self, "Update available", summary + "\n\nOpen GitHub Releases to download the portable package?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if answer == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(release_url))
            return

        answer = QMessageBox.question(
            self, "Update available", summary + "\n\nDownload and install this update now? The application will close automatically after verification.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if answer != QMessageBox.Yes:
            self.status.setText("Update postponed.")
            return
        self.start_update_download(version, asset_url, asset_size, asset_digest)

    def start_update_download(self, version, asset_url, asset_size, asset_digest):
        progress = QProgressDialog("Preparing update download…", "Cancel", 0, 100, self)
        progress.setWindowTitle(f"Downloading GNS Downloader {version}")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        self._update_progress = progress
        worker = GitHubUpdateDownloadWorker(asset_url, asset_size, asset_digest)
        self._update_download_worker = worker
        worker.progress.connect(self.on_update_download_progress)
        worker.downloaded.connect(self.on_update_downloaded)
        worker.failed.connect(self.on_update_download_failed)
        worker.canceled.connect(self.on_update_download_canceled)
        progress.canceled.connect(worker.cancel)
        self.status.setText(f"Downloading update {version}…")
        progress.show()
        worker.start()

    def on_update_download_progress(self, downloaded, total, speed):
        progress = getattr(self, "_update_progress", None)
        if progress is None:
            return
        if total > 0:
            percent = min(100, int(downloaded * 100 / total))
            progress.setRange(0, 100)
            progress.setValue(percent)
            progress.setLabelText(
                f"Downloaded {format_bytes(downloaded)} of {format_bytes(total)} "
                f"({percent}%)\nSpeed: {format_bytes(speed)}/s"
            )
        else:
            progress.setRange(0, 0)
            progress.setLabelText(f"Downloaded {format_bytes(downloaded)}\nSpeed: {format_bytes(speed)}/s")

    def on_update_download_failed(self, message):
        progress = getattr(self, "_update_progress", None)
        if progress is not None:
            progress.close()
        self.status.setText("Update download failed.")
        QMessageBox.warning(self, "Update download failed", message)

    def on_update_download_canceled(self):
        progress = getattr(self, "_update_progress", None)
        if progress is not None:
            progress.close()
        self.status.setText("Update download canceled.")

    def on_update_downloaded(self, installer_path):
        progress = getattr(self, "_update_progress", None)
        if progress is not None:
            progress.close()
        # Consent was requested before download; launch after verification without a second prompt.
        active_states = ("Downloading", "Checking server", "Retrying", "Checking metadata", "Seeding", "Paused")
        active_downloads = [
            task.get("name", "download")
            for task in self.tasks.values()
            if task.get("status") in active_states
        ]
        if active_downloads:
            QMessageBox.information(
                self, "Update postponed",
                "Finish or cancel active downloads before installing the update.\n\n"
                + "Active downloads: " + ", ".join(active_downloads[:5])
            )
            try:
                os.remove(installer_path)
            except OSError:
                pass
            self.status.setText("Update downloaded; installation postponed until downloads finish.")
            return
        if not self.close():
            try:
                os.remove(installer_path)
            except OSError:
                pass
            self.status.setText("Update postponed because the application could not close.")
            return
        try:
            subprocess.Popen([installer_path], close_fds=True)
        except OSError as exc:
            QMessageBox.warning(self, "Could not launch Setup", str(exc))


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
            if category.startswith("Category:") and (task.get("category") or category_for_filename(task.get("name", ""))) != category.split(":", 1)[1]:
                continue
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

        remove_action = menu.addAction("Remove from list")
        remove_action.setToolTip("Remove the download entry without deleting the downloaded file")
        remove_action.triggered.connect(self.remove_selected)

        delete_file_action = menu.addAction("Delete file from disk…")
        file_path = task.get("path", "")
        delete_file_action.setEnabled(
            status == "Completed" and bool(file_path) and os.path.isfile(file_path)
        )
        delete_file_action.setToolTip("Permanently delete the downloaded file from your drive")
        delete_file_action.triggered.connect(self.delete_file_selected)

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
                    self._send(200, {"ok": True, "app": APP_NAME, "version": APP_VERSION})
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
                    self._send(202, {"ok": True, "message": f"Added to {APP_NAME} queue"})
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

    def open_website_downloader(self):
        self.tabs.setCurrentWidget(self.website_page)

    def add_website_downloads(self, urls_and_names, destination_folder):
        """Queue reviewed website resources in the site's dedicated folder."""
        os.makedirs(destination_folder, exist_ok=True)
        added = 0
        for url, suggested_name in urls_and_names:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
            task_id = uuid.uuid4().hex
            name = os.path.basename(urllib.parse.unquote(parsed.path)) or suggested_name or "Download"
            self.tasks[task_id] = {
                "id": task_id, "url": url, "folder": destination_folder,
                "name": name, "status": "Queued", "downloaded": 0, "total": 0,
                "speed": 0.0, "eta": -1.0, "path": "", "worker": None,
                "history": False, "scheduled_at": "",
                "category": category_for_filename(name),
                "post_action_enabled": False, "post_action": "none", "post_action_done": False
            }
            added += 1
        if added:
            self.save_tasks()
            self.refresh_table()
            self.start_queue()
        return added

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
        name = os.path.basename(urllib.parse.unquote(parsed.path)) or "Download"
        name = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .") or "Download"
        normalized_url = urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
        for existing in self.tasks.values():
            same_url = existing.get("url") == normalized_url
            same_target = (existing.get("folder") == folder and existing.get("name", "").casefold() == name.casefold())
            if (same_url or same_target) and existing.get("status") not in ("Failed", "Canceled"):
                QMessageBox.information(self, "Duplicate download", "This URL or target filename is already in the download list: " + existing.get("name", "Download"))
                return
        self.tasks[task_id] = {
            "id": task_id, "url": url, "folder": folder, "name": name,
            "status": "Checking metadata", "downloaded": 0, "total": 0,
            "speed": 0.0, "eta": -1.0, "path": "",
            "worker": None, "history": False, "metadata_worker": None,
            "scheduled_at": "", "total_known": False,
            "category": category_for_filename(name),
            "post_action_enabled": False, "post_action": "none", "post_action_done": False
        }
        self.save_tasks()
        self.url.clear()
        self.status.setText("Checking file information before download…")
        self.probe_download_task(task_id)

    def probe_download_task(self, task_id):
        task = self.tasks.get(task_id)
        if not task:
            return
        worker = FileInfoWorker(task["url"])
        task["metadata_worker"] = worker
        worker.info_ready.connect(lambda info, tid=task_id: self.on_file_info_ready(tid, info))
        worker.finished.connect(lambda tid=task_id, current=worker: self._metadata_worker_finished(tid, current))
        worker.start()
        self.show_download_details(task_id)
        self.refresh_table()

    def _metadata_worker_finished(self, task_id, worker):
        task = self.tasks.get(task_id)
        if task and task.get("metadata_worker") is worker:
            task["metadata_worker"] = None

    def on_file_info_ready(self, task_id, info):
        task = self.tasks.get(task_id)
        if not task:
            return
        if task.get("status") in ("Canceled", "Canceling"):
            return
        if info.get("error"):
            task.update({"status": "Failed", "speed": 0.0, "eta": -1.0})
            self.save_history_entry(task, error=info["error"])
            self.save_tasks()
            self.refresh_table()
            self.status.setText(f"Could not read download information: {info['error']}")
            return
        if info.get("name"):
            task["name"] = info["name"]
        task["total"] = max(0, int(info.get("size", -1)))
        task["total_known"] = task["total"] > 0
        task["content_type"] = info.get("content_type", "") or "Unknown"
        task["accept_ranges"] = bool(info.get("accept_ranges"))
        task["status"] = "Ready"
        task["category"] = category_for_filename(task["name"])
        self.save_tasks()
        self.refresh_table()
        self.show_download_details(task_id)
        self.status.setText(
            f"File information ready: {task['name']} — "
            f"{format_bytes(task['total']) if task['total'] else 'Size unknown'}. Press Start to download."
        )

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
        self.tasks[task_id] = {
            "id": task_id, "url": source, "folder": folder, "name": name,
            "status": "Queued", "downloaded": 0, "total": 0, "speed": 0.0,
            "eta": -1.0, "path": "", "worker": None, "history": False,
            "kind": "torrent", "category": "Torrent", "upload_speed": 0.0,
            "scheduled_at": "",
            "post_action_enabled": False, "post_action": "none", "post_action_done": False
        }
        self.save_tasks()
        self.refresh_table()
        self.status.setText("Torrent added to queue. Set its start time in the Schedule tab if needed.")
        self.start_queue()
    def start_queue(self):
        self.schedule_downloads()

    def schedule_downloads(self):
        active = sum(1 for task in self.tasks.values() if task["status"] in ("Downloading", "Paused", "Checking server", "Retrying", "Seeding"))
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
                worker = DownloadWorker(task_id, task["url"], task["folder"], self.speed_limit.value(), self.parts_count.value())
            task["worker"] = worker
            self.workers[task_id] = worker
            worker.progress.connect(self.on_progress)
            if hasattr(worker, "parts_configured"):
                worker.parts_configured.connect(lambda count, tid=task_id: self.on_parts_configured(tid, count))
            worker.completed.connect(self.on_completed)
            worker.failed.connect(self.on_failed)
            worker.canceled.connect(self.on_canceled)
            worker.state.connect(lambda value, tid=task_id: self.on_state(tid, value))
            task["status"] = "Downloading"
            self.show_download_details(task_id)
            worker.start()
            active += 1
        self.refresh_table()

    def show_download_details(self, task_id):
        task = self.tasks.get(task_id)
        if not task:
            return
        dialog = self.detail_windows.get(task_id)
        if dialog is not None:
            dialog.refresh_data()
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog = DownloadDetailsDialog(self, task)
        self.detail_windows[task_id] = dialog
        dialog.destroyed.connect(
            lambda _=None, tid=task_id: self.detail_windows.pop(tid, None)
        )
        dialog.show()

    def open_or_show_download(self, row, column):
        file_cell = self.table.cellWidget(row, 0)
        task_id = file_cell.property("task_id") if file_cell else None
        if not task_id or task_id not in self.tasks:
            return
        self.table.setCurrentCell(row, 0)
        self.show_download_details(task_id)

    def parts_tooltip(self, task):
        """Build a live hover summary of the download's parallel segments."""
        if task.get("kind") == "torrent":
            return "Torrent task\nHover details: torrent progress and seeding status are shown in the row."
        if task.get("status") == "Completed":
            return "Download completed\nDouble-click to open the downloaded file."
        total = int(task.get("total") or 0)
        count = min(int(task.get("parts_count") or CONNECTIONS), total) if total > 0 else CONNECTIONS
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
        file_cell = self.table.cellWidget(row, 0)
        return file_cell.property("task_id") if file_cell else None

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
        self.cancel_task(task_id)

    def _cleanup_task_artifacts(self, task_id, task=None):
        task = task or self.tasks.get(task_id, {})
        folder = task.get("folder", "")
        if not folder:
            return
        parts_dir = os.path.join(folder, f".fdmx_{task_id}.parts")
        if os.path.isdir(parts_dir):
            shutil.rmtree(parts_dir, ignore_errors=True)
        worker = task.get("worker")
        partials = (getattr(worker, "temp_path", None), task.get("temp_path"))
        suffix = f".{task_id}.fdmx.tmp"
        try:
            for name in os.listdir(folder):
                if name.endswith(suffix):
                    partials += (os.path.join(folder, name),)
        except OSError:
            pass
        for partial in partials:
            if partial and os.path.isfile(partial):
                try:
                    os.remove(partial)
                except OSError:
                    pass

    def cancel_task(self, task_id):
        task = self.tasks.get(task_id)
        if not task:
            return
        metadata_worker = task.get("metadata_worker")
        worker = task.get("worker")
        if metadata_worker is not None:
            try:
                metadata_worker.cancel()
            except Exception:
                pass
        if worker is not None and worker.isRunning():
            task["status"] = "Canceling"
            self.save_tasks()
            worker.cancel()
        else:
            task.update({"status": "Canceled", "worker": None, "speed": 0.0, "eta": -1.0})
            self._cleanup_task_artifacts(task_id, task)
            self.save_history_entry(task)
            self.save_tasks()
            self.schedule_downloads()
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
        if task and (task.get("worker") is not None or task.get("metadata_worker") is not None):
            worker = task.get("worker") or task.get("metadata_worker")
            if worker.isRunning():
                QMessageBox.information(self, "Download active", "Cancel the active download before removing it.")
                return
        self._cleanup_task_artifacts(task_id, task)
        self.tasks.pop(task_id, None)
        self.save_tasks()
        self.refresh_table()

    def delete_file_selected(self):
        """Delete a completed download from disk, then remove its list entry."""
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if not task:
            return
        active_states = ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding")
        if task.get("status") in active_states:
            QMessageBox.information(self, "Download active", "Cancel the active download before deleting its file.")
            return
        path = task.get("path", "")
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, "File not found", "The downloaded file could not be found on disk.")
            return
        answer = QMessageBox.question(
            self,
            "Delete downloaded file",
            f"Permanently delete this file from your drive?\n\n{path}\n\n"
            "This action permanently removes the file. Its entry will also be removed from the download list.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            os.remove(path)
        except OSError as exc:
            QMessageBox.warning(self, "Delete failed", f"Could not delete the file:\n{exc}")
            return
        self.tasks.pop(task_id, None)
        self.save_tasks()
        self.refresh_table()
        self.status.setText(f"Deleted from disk: {path}")

    def on_parts_configured(self, task_id, count):
        task = self.tasks.get(task_id)
        if not task:
            return
        task["parts_count"] = int(count)
        self.save_tasks()
        dialog = self.detail_windows.get(task_id)
        if dialog is not None:
            dialog.refresh_data()
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
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray.showMessage(f"{APP_NAME} — Download complete", task.get("name", "Download"), QSystemTrayIcon.Information, 4000)
        self.cleanup_worker(task_id)
        self.schedule_downloads()
        self.run_task_post_action(task)

    def on_failed(self, message):
        task_id = self.sender().task_id
        task = self.tasks.get(task_id)
        if task:
            task.update({"status": "Failed", "speed": 0.0, "eta": -1.0, "worker": None})
            self.save_history_entry(task, error=message)
            self.refresh_table()
            attempts = int(task.get("retry_attempts", 0)) if task else 0
        if task and attempts < 3:
            attempts += 1
            task["retry_attempts"] = attempts
            task["status"] = "Retrying"
            self.save_tasks()
            delay = min(60, 5 * (2 ** (attempts - 1)))
            self.status.setText(f"Network error. Automatic retry {attempts}/3 in {delay}s…")
            QTimer.singleShot(delay * 1000, lambda tid=task_id: self._auto_retry_task(tid))
        else:
            self.status.setText(f"Download failed: {message}")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.showMessage(f"{APP_NAME} — Download failed", task.get("name", "Download") if task else message, QSystemTrayIcon.Warning, 5000)
        self.cleanup_worker(task_id)
        self.schedule_downloads()
        QMessageBox.warning(self, "Download failed", message)

    def _auto_retry_task(self, task_id):
        task = self.tasks.get(task_id)
        if not task or task.get("status") != "Retrying":
            return
        task.update({"status": "Queued", "downloaded": 0, "total": 0, "speed": 0.0, "eta": -1.0, "path": "", "worker": None})
        self.save_tasks()
        self.refresh_table()
        self.schedule_downloads()

    def on_canceled(self):
        worker = self.sender()
        task_id = worker.task_id
        task = self.tasks.get(task_id)
        if task:
            task.update({"status": "Canceled", "speed": 0.0, "eta": -1.0, "worker": None})
            self._cleanup_task_artifacts(task_id, task)
            self.save_history_entry(task)
            self.save_tasks()
            self.refresh_table()
        self.cleanup_worker(task_id)
        self.schedule_downloads()

    def cleanup_worker(self, task_id):
        worker = self.workers.pop(task_id, None)
        if worker:
            worker.deleteLater()

    def update_row(self, task_id):
        for row in range(self.table.rowCount()):
            file_cell = self.table.cellWidget(row, 0)
            if file_cell and file_cell.property("task_id") == task_id:
                self.fill_row(row, self.tasks[task_id])
                break
        self.update_summary()

    def refresh_table(self):
        visible = self.visible_tasks()
        self.table.setRowCount(len(visible))
        for row, (task_id, task) in enumerate(visible):
            self.fill_row(row, task)
        self.update_summary()
        self.refresh_analytics()

    def fill_row(self, row, task):
        values = [
            "", task['status'],
            f"{format_bytes(task['downloaded'])} / {format_bytes(task['total'])}" if task['total'] else format_bytes(task['downloaded']),
            format_bytes(task['speed']) + '/s',
            format_duration(task['eta'])
        ]
        hover_text = self.parts_tooltip(task)
        # Column 0 is a custom widget; do not create a table item underneath it.
        # This prevents the filename from being painted twice by Qt.
        for col in range(1, len(values)):
            item = QTableWidgetItem(values[col])
            item.setToolTip(hover_text)
            if col == 1:
                status_colors = {"Downloading":"#16803c","Completed":"#16803c","Paused":"#b7791f","Queued":"#2563eb","Ready":"#2563eb","Failed":"#dc2626","Canceled":"#6b7280","Retrying":"#d97706","Checking metadata":"#0ea5e9","Checking server":"#0ea5e9","Seeding":"#7c3aed"}
                item.setForeground(QColor(status_colors.get(task.get("status"), "#64748b")))
            if col in (2, 3, 4):
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)

        category = task.get('category') or category_for_filename(task['name'])
        type_icons = {'Video': '🎬', 'Audio': '🎵', 'Documents': '📄', 'Programs': '💿', 'Images': '🖼️', 'Spreadsheets': '📊', 'Code': '</>', 'Other': '📁'}
        bar = QProgressBar()
        bar.setRange(0, 100)
        percent = int(task['downloaded'] * 100 / task['total']) if task['total'] else 0
        bar.setValue(min(100, percent))
        bar.setFormat(f'{min(100, percent)}%')
        bar.setToolTip(hover_text)
        name_row = QWidget()
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(7)
        if category in ("Compressed", "Python", "Video", "Audio", "Documents", "Programs", "Images", "Spreadsheets", "Code"):
            icon_label = QLabel()
            icon_label.setFixedSize(26, 26)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(create_file_type_icon(category).pixmap(24, 24))
            name_layout.addWidget(icon_label)
        else:
            icon_label = QLabel(type_icons.get(category, '📁'))
            icon_label.setFixedWidth(24)
            icon_label.setAlignment(Qt.AlignCenter)
            name_layout.addWidget(icon_label)
        name_label = QLabel(task['name'])
        name_label.setStyleSheet('font-weight:600;padding-left:1px;')
        name_label.setToolTip(hover_text)
        name_layout.addWidget(name_label, 1)
        file_cell = QWidget()
        file_cell.setProperty("task_id", task['id'])
        file_layout = VBoxLayout(file_cell)
        file_layout.setContentsMargins(4, 3, 4, 3)
        file_layout.setSpacing(2)
        file_layout.addWidget(name_row)
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
        """Restore pending tasks, falling back to the last known-good checkpoint."""
        saved = None
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
            if not isinstance(saved, list):
                raise ValueError("Task snapshot must be a list")
        except (OSError, ValueError, TypeError):
            try:
                with open(TASKS_BACKUP_FILE, "r", encoding="utf-8") as file:
                    saved = json.load(file)
                if not isinstance(saved, list):
                    raise ValueError("Backup snapshot must be a list")
            except (OSError, ValueError, TypeError):
                saved = []

        self.recovered_task_ids = set()
        interrupted_states = ("Downloading", "Checking server", "Retrying", "Seeding")
        for entry in saved:
            if not isinstance(entry, dict) or not entry.get("url") or not entry.get("folder"):
                continue
            task_id = entry.get("id") or uuid.uuid4().hex
            if task_id in self.tasks:
                continue
            original_status = entry.get("status", "Queued")
            status = original_status
            if status == "Checking metadata":
                status = "Ready"
            elif status in interrupted_states:
                # Keep interrupted tasks paused until the user confirms recovery.
                status = "Paused"
                self.recovered_task_ids.add(task_id)
            self.tasks[task_id] = {
                "id": task_id, "url": entry["url"], "folder": entry["folder"],
                "name": entry.get("name", "Download"), "status": status,
                "downloaded": entry.get("downloaded", 0), "total": entry.get("total", 0),
                "speed": 0.0, "eta": -1.0, "path": entry.get("path", ""),
                "worker": None, "history": False,
                "content_type": entry.get("content_type", "Unknown"),
                "kind": entry.get("kind", "http"),
                "scheduled_at": entry.get("scheduled_at", ""),
                "category": entry.get("category") or category_for_filename(entry.get("name", "")),
                "retry_attempts": int(entry.get("retry_attempts", 0)),
                "post_action_enabled": bool(entry.get("post_action_enabled", False)),
                "post_action": entry.get("post_action", "none"),
                "post_action_done": bool(entry.get("post_action_done", False)),
                "parts_count": int(entry.get("parts_count", 0) or 0),
            }

    def prompt_recovery(self):
        """Ask before restarting downloads that were active in the previous session."""
        recovered = [self.tasks[task_id] for task_id in self.recovered_task_ids if task_id in self.tasks]
        if not recovered:
            return
        answer = QMessageBox.question(
            self, "Recover interrupted downloads",
            f"{APP_NAME} found {len(recovered)} interrupted download(s). Resume them now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if answer == QMessageBox.Yes:
            for task in recovered:
                task["status"] = "Queued"
            self.status.setText(f"Recovery accepted: {len(recovered)} download(s) queued.")
        else:
            self.status.setText(f"Recovery postponed: {len(recovered)} download(s) remain paused.")
        self.save_tasks()
        self.refresh_table()

    def save_tasks(self):
        """Atomically save task metadata and retain a last-known-good backup snapshot."""
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        saved = []
        for task in self.tasks.values():
            if task.get("status") in ("Completed", "Failed", "Canceled", "Canceling"):
                continue
            saved.append({key: task.get(key) for key in (
                "id", "url", "folder", "name", "status", "downloaded", "total", "path",
                "category", "kind", "scheduled_at", "content_type", "retry_attempts",
                "post_action_enabled", "post_action", "post_action_done",
                "parts_count"
            )})
        temp_path = TASKS_FILE + ".tmp"
        backup_temp = TASKS_BACKUP_FILE + ".tmp"
        try:
            # Preserve the previous valid snapshot before replacing it.
            if os.path.isfile(TASKS_FILE):
                try:
                    shutil.copyfile(TASKS_FILE, backup_temp)
                    os.replace(backup_temp, TASKS_BACKUP_FILE)
                except OSError:
                    try:
                        if os.path.exists(backup_temp):
                            os.remove(backup_temp)
                    except OSError:
                        pass
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(saved, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, TASKS_FILE)
        except OSError as exc:
            if hasattr(self, "status"):
                self.status.setText(f"Could not save pending downloads: {exc}")
            for path in (temp_path, backup_temp):
                try:
                    if os.path.exists(path):
                        os.remove(path)
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
        self.parts_count.setValue(max(1, min(MAX_PARTS, self.settings.value("parts_count", CONNECTIONS, type=int))))
        self.speed_limit.setValue(self.settings.value("speed_limit", 0, type=int))
        self.torrent_upload_limit.setValue(self.settings.value("torrent_upload_limit", 1, type=int))
        default_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        self.folder.setText(self.settings.value("download_folder", default_folder, type=str))
        self.max_downloads.valueChanged.connect(self.save_preferences)
        self.parts_count.valueChanged.connect(self.save_preferences)
        self.speed_limit.valueChanged.connect(self.save_preferences)
        self.torrent_upload_limit.valueChanged.connect(self.save_preferences)
        self.folder.editingFinished.connect(self.save_preferences)
        self.clipboard_monitor.setChecked(self.settings.value("clipboard_monitor", False, type=bool))
        default_theme = "ubuntu_yaru" if sys.platform.startswith("linux") else "fluent"
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(default_theme)))
        self.settings.setValue("theme", default_theme)
        self.apply_selected_theme()
        self.proxy_enabled.setChecked(self.settings.value("proxy_enabled", False, type=bool))
        self.proxy_url.setText(self.settings.value("proxy_url", "", type=str))
        self.proxy_enabled.toggled.connect(self.save_preferences)
        self.proxy_url.editingFinished.connect(self.save_preferences)
        self.apply_proxy_settings()

    def save_preferences(self):
        """Persist preferences without touching queued or active download data."""
        if not hasattr(self, "settings"):
            return
        self.settings.setValue("max_downloads", self.max_downloads.value())
        self.settings.setValue("parts_count", self.parts_count.value())
        self.settings.setValue("speed_limit", self.speed_limit.value())
        self.settings.setValue("torrent_upload_limit", self.torrent_upload_limit.value())
        self.settings.setValue("download_folder", self.folder.text().strip())
        self.settings.setValue("clipboard_monitor", self.clipboard_monitor.isChecked())
        self.settings.setValue("proxy_enabled", self.proxy_enabled.isChecked())
        self.settings.setValue("proxy_url", self.proxy_url.text().strip())
        self.settings.sync()
        self.apply_proxy_settings()

    def apply_proxy_settings(self):
        """Apply the optional HTTP/HTTPS proxy to urllib-based downloads."""
        if self.proxy_enabled.isChecked() and self.proxy_url.text().strip():
            proxy = self.proxy_url.text().strip()
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            urllib.request.install_opener(build_url_opener(handler))
        else:
            urllib.request.install_opener(build_url_opener())

    def run_task_post_action(self, task):
        """Run the action configured for this one task, at most once."""
        if not task or not task.get("post_action_enabled") or task.get("post_action_done"):
            return
        action = task.get("post_action", "none")
        if action == "none":
            return
        if os.name != "nt":
            self.status.setText("Post-download power actions are available on Windows only.")
            task["post_action_done"] = True
            self.save_tasks()
            return
        commands = {
            "shutdown": ["shutdown", "/s", "/t", "30"],
            "logout": ["shutdown", "/l"],
            "hibernate": ["shutdown", "/h"]
        }
        command = commands.get(action)
        if not command:
            return
        task["post_action_done"] = True
        self.save_tasks()
        labels = {"shutdown": "shut down", "logout": "log out", "hibernate": "hibernate"}
        self.status.setText(f"Download completed. Windows will {labels[action]} shortly.")
        subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def update_torrent_upload_limit(self, value):
        for worker in self.workers.values():
            if isinstance(worker, TorrentWorker):
                worker.set_upload_limit(value)
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
            expected, accepted = QInputDialog.getText(self, "Verify SHA-256", "Expected SHA-256 (leave blank to calculate only):")
            if not accepted:
                return
            expected = expected.strip().lower()
            if expected and not re.fullmatch(r"[0-9a-f]{64}", expected):
                QMessageBox.warning(self, "Invalid hash", "Enter exactly 64 hexadecimal characters.")
                return
            if expected:
                result = "MATCH — integrity verified." if value.lower() == expected else "MISMATCH — hash does not match."
                QMessageBox.information(self, "SHA-256 verification", f"{result}\n\nCalculated: {value}\nExpected: {expected}")
            else:
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
        metadata_pending = [
            task for task in self.tasks.values()
            if task.get("metadata_worker") and task["metadata_worker"].isRunning()
        ]
        active = [
            task for task in self.tasks.values()
            if task.get("worker")
            and task.get("status") in ("Downloading", "Paused", "Checking server", "Retrying", "Checking metadata", "Seeding")
        ]
        for task in metadata_pending:
            task["metadata_worker"].cancel()
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
                worker = task.get("worker") or task.get("metadata_worker")
                if worker:
                    worker.cancel()
            for task in active:
                worker = task.get("worker") or task.get("metadata_worker")
                if worker:
                    worker.wait(5000)
                if task.get("status") not in ("Canceled", "Completed"):
                    task.update({"status": "Canceled", "worker": None, "speed": 0.0, "eta": -1.0})
                    self._cleanup_task_artifacts(task.get("id"), task)
                    self.save_history_entry(task)
        for task in metadata_pending:
            worker = task.get("metadata_worker")
            if worker:
                worker.wait(5000)
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