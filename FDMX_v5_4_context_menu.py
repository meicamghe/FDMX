import sys
import os
import re
import json
import time
import uuid
import hashlib
import mimetypes
import threading
import select
import tempfile
import urllib.request
import urllib.parse
from email.message import Message
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QMenu, QSpinBox,
    QDoubleSpinBox, QHeaderView, QAbstractItemView, QGroupBox
)


APP_NAME = "FDMX"
APP_VERSION = "5.4"
CONNECTIONS = 8
CHUNK_SIZE = 64 * 1024
READ_POLL_INTERVAL = 0.2  # seconds; pause responsiveness while waiting for network data
HISTORY_FILE = os.path.join(
    os.path.expanduser("~"), ".fdmx", "history.json"
)


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
        headers = {"User-Agent": f"FDMX/{APP_VERSION}"}
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
                    "User-Agent": f"FDMX/{APP_VERSION}",
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

        with tempfile.TemporaryDirectory(prefix="fdmx_", dir=self.folder) as temp_folder:
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
            with self.request(0, 0) as probe:
                filename = get_filename(probe)
                content_range = probe.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes 0-0/(\d+)", content_range)
                supported = probe.status == 206 and match is not None
                total = int(match.group(1)) if match else 0
                probe.read(1)

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


class FDMX(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"FDMX - Download Manager {APP_VERSION}")
        self.resize(1050, 620)
        self.tasks = {}
        self.workers = {}
        self.history = []
        self._loading = False
        self.load_history()
        self.build_ui()
        self.refresh_table()
        self.scheduler_timer = self.startTimer(400)

    def build_ui(self):
        root = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title = QLabel(f"FDMX Download Manager  v{APP_VERSION}")
        title.setStyleSheet("font-size:24px;font-weight:700;")
        title_row.addWidget(title)
        title_row.addStretch()
        self.summary = QLabel("Ready")
        title_row.addWidget(self.summary)
        root.addLayout(title_row)

        add_group = QGroupBox("New download")
        add_layout = QGridLayout(add_group)
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste HTTP or HTTPS download URL...")
        self.folder = QLineEdit(os.path.join(os.path.expanduser("~"), "Downloads"))
        browse = QPushButton("Browse")
        browse.clicked.connect(self.select_folder)
        add_layout.addWidget(QLabel("URL"), 0, 0)
        add_layout.addWidget(self.url, 0, 1, 1, 4)
        add_layout.addWidget(QLabel("Save to"), 1, 0)
        add_layout.addWidget(self.folder, 1, 1, 1, 3)
        add_layout.addWidget(browse, 1, 4)
        self.add_button = QPushButton("Add to queue")
        self.add_button.clicked.connect(self.add_download)
        add_layout.addWidget(self.add_button, 2, 4)
        root.addWidget(add_group)

        settings = QHBoxLayout()
        settings.addWidget(QLabel("Maximum simultaneous downloads:"))
        self.max_downloads = QSpinBox()
        self.max_downloads.setRange(1, 10)
        self.max_downloads.setValue(2)
        settings.addWidget(self.max_downloads)
        settings.addSpacing(18)
        settings.addWidget(QLabel("Speed limit per file (KB/s, 0 = unlimited):"))
        self.speed_limit = QSpinBox()
        self.speed_limit.setRange(0, 10_000_000)
        self.speed_limit.setValue(0)
        settings.addWidget(self.speed_limit)
        settings.addStretch()
        root.addLayout(settings)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "File", "Status", "Progress", "Downloaded / Size",
            "Speed", "Time left", "Location"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        root.addWidget(self.table, 1)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Start queue")
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.cancel_button = QPushButton("Cancel")
        self.retry_button = QPushButton("Retry")
        self.remove_button = QPushButton("Remove")
        self.hash_button = QPushButton("SHA-256")
        self.open_button = QPushButton("Open folder")
        for button, callback in [
            (self.start_button, self.start_queue),
            (self.pause_button, self.pause_selected),
            (self.resume_button, self.resume_selected),
            (self.cancel_button, self.cancel_selected),
            (self.retry_button, self.retry_selected),
            (self.remove_button, self.remove_selected),
            (self.hash_button, self.calculate_hash),
            (self.open_button, self.open_folder),
        ]:
            button.clicked.connect(callback)
            controls.addWidget(button)
        root.addLayout(controls)

        self.status = QLabel("Ready — add a URL to begin.")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.status)

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
        active = status in ("Downloading", "Paused", "Checking server", "Retrying")
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

    def add_download(self):
        url = self.url.text().strip()
        folder = self.folder.text().strip()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            QMessageBox.warning(self, "Invalid URL", "Enter a valid HTTP or HTTPS URL.")
            return
        if not folder:
            QMessageBox.warning(self, "Folder required", "Select a download folder.")
            return
        os.makedirs(folder, exist_ok=True)
        task_id = uuid.uuid4().hex
        self.tasks[task_id] = {
            "id": task_id, "url": url, "folder": folder,
            "name": os.path.basename(urllib.parse.unquote(parsed.path)) or "Download",
            "status": "Queued", "downloaded": 0, "total": 0,
            "speed": 0.0, "eta": -1.0, "path": "",
            "worker": None, "history": False
        }
        self.url.clear()
        self.refresh_table()
        self.status.setText("Added to queue.")
        self.start_queue()

    def start_queue(self):
        self.schedule_downloads()

    def schedule_downloads(self):
        active = sum(1 for task in self.tasks.values() if task["status"] in ("Downloading", "Paused", "Checking server", "Retrying"))
        capacity = self.max_downloads.value()
        if active >= capacity:
            return
        for task_id, task in list(self.tasks.items()):
            if active >= capacity:
                break
            if task["status"] != "Queued":
                continue
            worker = DownloadWorker(
                task_id, task["url"], task["folder"], self.speed_limit.value()
            )
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

    def selected_task(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def pause_selected(self):
        task_id = self.selected_task()
        task = self.tasks.get(task_id)
        if task and task.get("worker") and task["status"] == "Downloading":
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
        if task and task["status"] in ("Downloading", "Paused", "Checking server", "Retrying"):
            QMessageBox.information(self, "Download active", "Cancel the active download before removing it.")
            return
        self.tasks.pop(task_id, None)
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
            task["status"] = state
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
        self.table.setRowCount(len(self.tasks))
        for row, (task_id, task) in enumerate(self.tasks.items()):
            self.fill_row(row, task)
        self.update_summary()

    def fill_row(self, row, task):
        values = [
            task["name"], task["status"],
            f'{int(task["downloaded"] * 100 / task["total"])}%' if task["total"] else "—",
            f'{format_bytes(task["downloaded"])} / {format_bytes(task["total"])}' if task["total"] else format_bytes(task["downloaded"]),
            format_bytes(task["speed"]) + "/s",
            format_duration(task["eta"]),
            task["folder"]
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col == 0:
                item.setData(Qt.UserRole, task["id"])
            if col in (2, 3, 4, 5):
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, col, item)
        bar = QProgressBar()
        bar.setRange(0, 100)
        percent = int(task["downloaded"] * 100 / task["total"]) if task["total"] else 0
        bar.setValue(min(100, percent))
        self.table.setCellWidget(row, 2, bar)

    def update_summary(self):
        active = sum(1 for t in self.tasks.values() if t["status"] in ("Downloading", "Paused", "Checking server", "Retrying"))
        queued = sum(1 for t in self.tasks.values() if t["status"] == "Queued")
        done = sum(1 for t in self.tasks.values() if t["status"] == "Completed")
        self.summary.setText(f"Active: {active}   Queued: {queued}   Completed: {done}")

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
            if task.get("worker") and task["status"] in ("Downloading", "Paused", "Checking server", "Retrying")
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
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FDMX()
    window.show()
    sys.exit(app.exec())
