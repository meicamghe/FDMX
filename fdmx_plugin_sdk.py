"""FDMX Plugin SDK 1.5 - signed plugins, lifecycle, and atomic updates.
Plugins run in a separate process. This is crash containment, NOT an OS sandbox.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, threading, uuid, hashlib, base64

from dataclasses import dataclass
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QTextEdit, QMessageBox, QFileDialog

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    CRYPTO_AVAILABLE = True
except ImportError:
    serialization = Ed25519PrivateKey = Ed25519PublicKey = None
    CRYPTO_AVAILABLE = False

SDK_VERSION = "1.5"
ALLOWED_PERMISSIONS = {"app.events", "app.log", "ui.notifications"}
PLUGIN_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
MAX_MESSAGE_BYTES = 1024 * 1024
ALLOWED_EVENTS = {"app.started", "download.completed", "download.failed"}


SIGNATURE_FILE = "plugin.sig"
SIGNATURE_FORMAT = "FDMX-PLUGIN-SIGNATURE-V1"


def _require_crypto():
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("Ed25519 signing and verification requires the 'cryptography' package")


def _plugin_file_hashes(folder):
    root = Path(folder)
    hashes = {}
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError("Plugin packages may not contain symbolic links: " + str(path))
        if path.is_file() and path.relative_to(root).as_posix() != SIGNATURE_FILE:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[path.relative_to(root).as_posix()] = digest.hexdigest()
        elif not path.is_dir() and not path.is_file():
            raise ValueError("Unsupported special file in plugin package: " + str(path))
    return hashes


def _signature_payload(fingerprint, files):
    value = {"format": SIGNATURE_FORMAT, "fingerprint": fingerprint, "files": files}
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_plugin_folder(folder, private_key_pem):
    """Sign every regular package file (except plugin.sig) with an Ed25519 PEM key."""
    _require_crypto()
    root = Path(folder).expanduser().resolve()
    if not root.is_dir() or not (root / "plugin.json").is_file():
        raise ValueError("A plugin folder with plugin.json is required")
    key_data = private_key_pem.encode("utf-8") if isinstance(private_key_pem, str) else private_key_pem
    key = serialization.load_pem_private_key(key_data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("Signing key must be Ed25519")
    public = key.public_key()
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    public_pem = public.public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    files = _plugin_file_hashes(root)
    signature = key.sign(_signature_payload(fingerprint, files))
    envelope = {"format": SIGNATURE_FORMAT, "algorithm": "Ed25519",
        "fingerprint": fingerprint, "public_key_pem": public_pem, "files": files,
        "signature": base64.b64encode(signature).decode("ascii")}
    target = root / SIGNATURE_FILE
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(envelope, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return fingerprint


def verify_plugin_folder(folder, trusted_publishers=None):
    """Verify signature and package hashes; unknown keys are never implicitly trusted."""
    root = Path(folder)
    signature_path = root / SIGNATURE_FILE
    if not signature_path.exists():
        return {"status": "unsigned", "fingerprint": "", "detail": "No detached signature"}
    if not CRYPTO_AVAILABLE:
        return {"status": "unavailable", "fingerprint": "", "detail": "Install cryptography to verify Ed25519 signatures"}
    try:
        if signature_path.is_symlink() or not signature_path.is_file():
            raise ValueError("Signature file must be a regular file")
        envelope = json.loads(signature_path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or envelope.get("format") != SIGNATURE_FORMAT:
            raise ValueError("Unsupported signature format")
        if envelope.get("algorithm") != "Ed25519":
            raise ValueError("Unsupported signature algorithm")
        public = serialization.load_pem_public_key(envelope["public_key_pem"].encode("ascii"))
        if not isinstance(public, Ed25519PublicKey):
            raise ValueError("Publisher key is not Ed25519")
        raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        fingerprint = hashlib.sha256(raw).hexdigest()
        if envelope.get("fingerprint") != fingerprint:
            raise ValueError("Publisher fingerprint does not match public key")
        files = envelope.get("files")
        if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            raise ValueError("Invalid signed file manifest")
        actual = _plugin_file_hashes(root)
        if actual != files:
            raise ValueError("Plugin files differ from the signed package")
        signature = base64.b64decode(envelope["signature"], validate=True)
        public.verify(signature, _signature_payload(fingerprint, files))
        if (trusted_publishers or {}).get(fingerprint) == envelope["public_key_pem"]:
            return {"status": "trusted", "fingerprint": fingerprint, "detail": "Signature valid; publisher trusted"}
        return {"status": "unknown_publisher", "fingerprint": fingerprint, "detail": "Signature valid; publisher not yet trusted"}
    except Exception as exc:
        return {"status": "invalid", "fingerprint": "", "detail": type(exc).__name__ + ": " + str(exc)[:400]}


@dataclass
class PluginRecord:
    plugin_id: str
    name: str
    version: str
    description: str
    folder: Path
    entrypoint: str
    permissions: tuple[str, ...]
    enabled: bool = False
    loaded: bool = False
    error: str = ""
    signature_status: str = "unsigned"
    publisher_fingerprint: str = ""

def _build_worker_command(record, host_script, *, frozen=None, executable=None, bundle_dir=None, platform=None):
    """Build a worker launch command for source and PyInstaller deployments."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    platform = platform or sys.platform
    arguments = [str(record.folder), record.entrypoint, record.plugin_id,
                 json.dumps(list(record.permissions))]
    if not frozen:
        if not Path(host_script).is_file():
            raise FileNotFoundError(f"Plugin worker host script is missing: {host_script}")
        return [executable, "-u", str(host_script), *arguments]

    worker_name = "fdmx_plugin_worker.exe" if platform.startswith("win") else "fdmx_plugin_worker"
    candidates = [Path(executable).resolve().parent / worker_name]
    if bundle_dir:
        bundled = Path(bundle_dir) / worker_name
        if bundled not in candidates:
            candidates.append(bundled)
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate), *arguments]
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        f"Packaged plugin worker '{worker_name}' was not found. "
        f"Place it beside the FDMX executable or bundle it with the application. Searched: {searched}"
    )


class _Worker:
    def __init__(self, record, logger, notifier):
        self.record, self.logger, self.notifier = record, logger, notifier
        self.process = None
        self.ready = threading.Event()
        self.start_error = None
        self.write_lock = threading.Lock()

    def _send(self, message):
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("Plugin IPC message exceeds 1 MiB")
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Plugin worker is not running")
        with self.write_lock:
            self.process.stdin.write(raw + "\n")
            self.process.stdin.flush()

    def start(self):
        host = Path(__file__).with_name("fdmx_plugin_host.py")
        command = _build_worker_command(self.record, host)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1
        )
        threading.Thread(target=self._read_loop, name=f"FDMXPlugin-{self.record.plugin_id}", daemon=True).start()
        if not self.ready.wait(8.0):
            self.stop()
            raise TimeoutError("Plugin worker startup exceeded 8 seconds")
        if self.start_error:
            self.stop()
            raise RuntimeError(self.start_error)
        if self.process.poll() is not None:
            raise RuntimeError("Plugin worker exited during startup")

    def _read_loop(self):
        try:
            for line in self.process.stdout:
                if len(line.encode("utf-8", errors="replace")) > MAX_MESSAGE_BYTES:
                    self.start_error = "Worker sent an oversized IPC message"
                    break
                try:
                    msg = json.loads(line)
                except Exception:
                    self.start_error = "Worker sent invalid JSON"
                    continue
                kind = msg.get("type")
                if kind == "ready":
                    self.ready.set()
                elif kind == "startup_error":
                    self.start_error = str(msg.get("message", "Plugin startup failed"))[:1000]
                    self.ready.set()
                elif kind == "rpc":
                    self._handle_rpc(msg)
                elif kind == "fatal":
                    self.start_error = str(msg.get("message", "Worker failed"))[:1000]
                    self.ready.set()
                    self.logger(f"Plugin {self.record.plugin_id}: {self.start_error}")
                elif kind == "log":
                    self.logger(f"[{self.record.plugin_id}] {str(msg.get('message', ''))[:1000]}")
        finally:
            self.ready.set()

    def _handle_rpc(self, msg):
        result = {"type": "rpc_result", "id": msg.get("id"), "ok": True}
        try:
            method = msg.get("method")
            if method == "log" and "app.log" in self.record.permissions:
                self.logger(f"[{self.record.plugin_id}] {str(msg.get('message', ''))[:1000]}")
            elif method == "notify" and "ui.notifications" in self.record.permissions:
                self.notifier(str(msg.get("title", ""))[:120], str(msg.get("message", ""))[:1000])
            else:
                raise PermissionError(f"RPC method not permitted: {method}")
        except Exception as exc:
            result.update(ok=False, error=str(exc)[:500])
        try:
            self._send(result)
        except Exception as exc:
            self.logger(f"Plugin IPC response failed: {exc}")

    def emit(self, event_name, payload):
        if "app.events" in self.record.permissions and event_name in ALLOWED_EVENTS:
            self._send({"type": "event", "name": event_name, "payload": payload})

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self._send({"type": "shutdown"})
                self.process.wait(timeout=2.0)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        if self.process:
            for stream in (self.process.stdin, self.process.stdout):
                try: stream.close()
                except Exception: pass

class PluginManager:
    def __init__(self, plugin_dir, logger=None, notifier=None):
        self.plugin_dir = Path(plugin_dir).expanduser()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.plugin_dir.parent / "plugin_state.json"
        self.trust_file = self.plugin_dir.parent / "trusted_publishers.json"
        self.trusted_publishers = self._read_trusted_publishers()
        self.logger = logger or (lambda message: None)
        self.notifier = notifier or (lambda title, message: None)
        self.records, self._workers = {}, {}
        self._state = self._read_state()

    def _read_trusted_publishers(self):
        try:
            data = json.loads(self.trust_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def trust_publisher(self, public_key_pem):
        _require_crypto()
        public = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        if not isinstance(public, Ed25519PublicKey):
            raise TypeError("Publisher key must be Ed25519")
        raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        fingerprint = hashlib.sha256(raw).hexdigest()
        canonical = public.public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        previous = dict(self.trusted_publishers)
        self.trusted_publishers[fingerprint] = canonical
        temp = self.trust_file.with_name(self.trust_file.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            self.trust_file.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(self.trusted_publishers, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, self.trust_file)
        except Exception:
            self.trusted_publishers = previous
            temp.unlink(missing_ok=True)
            raise
        self.scan()
        return fingerprint

    def trust_plugin_publisher(self, plugin_id):
        rec = self.records[plugin_id]
        envelope = json.loads((rec.folder / SIGNATURE_FILE).read_text(encoding="utf-8"))
        return self.trust_publisher(envelope["public_key_pem"])

    def _read_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError): return {}

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_name(self.state_file.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as stream:
                json.dump(self._state, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.state_file)
        except OSError:
            try: temp.unlink(missing_ok=True)
            except OSError: pass
            raise

    def plugin_data_dir(self, plugin_id):
        if not PLUGIN_ID_RE.fullmatch(str(plugin_id)):
            raise ValueError("Invalid plugin id")
        return self.plugin_dir.parent / "plugin_data" / plugin_id

    def get_plugin_settings(self, plugin_id):
        if not PLUGIN_ID_RE.fullmatch(str(plugin_id)):
            raise ValueError("Invalid plugin id")
        entry = self._state.get(plugin_id, {})
        settings = entry.get("settings", {}) if isinstance(entry, dict) else {}
        return dict(settings) if isinstance(settings, dict) else {}

    def set_plugin_settings(self, plugin_id, settings):
        if not PLUGIN_ID_RE.fullmatch(str(plugin_id)):
            raise ValueError("Invalid plugin id")
        if not isinstance(settings, dict):
            raise TypeError("Plugin settings must be a JSON object")
        # Validate JSON compatibility before mutating persistent state.
        clean = json.loads(json.dumps(settings, ensure_ascii=False))
        previous = json.loads(json.dumps(self._state))
        self._state.setdefault(plugin_id, {})["settings"] = clean
        try:
            self._save_state()
        except Exception:
            self._state = previous
            raise

    def install_plugin(self, source_folder, *, allow_untrusted=False):
        """Install a signed plugin; untrusted packages require explicit opt-in."""
        source = Path(source_folder).expanduser().resolve()
        if not source.is_dir():
            raise NotADirectoryError(f"Plugin source folder does not exist: {source}")
        manifest = source / "plugin.json"
        if not manifest.is_file() or manifest.is_symlink():
            raise ValueError("Plugin folder must contain a regular plugin.json file")
        for item in source.rglob("*"):
            if item.is_symlink():
                raise ValueError(f"Plugin packages may not contain symbolic links: {item}")
        verification = verify_plugin_folder(source, self.trusted_publishers)
        if verification["status"] == "invalid":
            raise PermissionError("Plugin signature verification failed: " + verification["detail"])
        if verification["status"] != "trusted" and not allow_untrusted:
            raise PermissionError("Plugin signature status is " + verification["status"] + ": " +
                verification["detail"] + ". Explicitly allow untrusted installation only if you accept the risk.")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Plugin manifest must be a JSON object")
        plugin_id = str(data.get("id", source.name))
        if not PLUGIN_ID_RE.fullmatch(plugin_id):
            raise ValueError("Invalid plugin id in manifest")
        entry = str(data.get("entrypoint", "plugin.py"))
        if Path(entry).name != entry or not entry.endswith(".py"):
            raise ValueError("Entrypoint must be a Python file directly inside the plugin folder")
        permissions = data.get("permissions", [])
        if not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions):
            raise ValueError("Plugin permissions must be a list of strings")
        unknown = set(permissions) - ALLOWED_PERMISSIONS
        if unknown:
            raise ValueError("Unknown permission(s): " + ", ".join(sorted(unknown)))
        if not (source / entry).is_file():
            raise FileNotFoundError(f"Plugin entrypoint not found: {entry}")
        target = self.plugin_dir / plugin_id
        if target.exists():
            raise FileExistsError(f"Plugin is already installed: {plugin_id}")
        staging = self.plugin_dir / (".install-" + uuid.uuid4().hex)
        try:
            shutil.copytree(source, staging)
            # Verify the copied bytes too, closing the source-to-staging modification window.
            staged_verification = verify_plugin_folder(staging, self.trusted_publishers)
            if staged_verification["status"] == "invalid":
                raise PermissionError("Staged plugin signature verification failed: " + staged_verification["detail"])
            if (staged_verification["status"], staged_verification["fingerprint"]) != (verification["status"], verification["fingerprint"]):
                raise RuntimeError("Plugin package changed during installation")
            # Re-validate the staged manifest before making it visible to scan().
            staged_manifest = json.loads((staging / "plugin.json").read_text(encoding="utf-8"))
            if str(staged_manifest.get("id", staging.name)) != plugin_id:
                raise ValueError("Plugin manifest changed during installation")
            os.replace(staging, target)
            self.scan()
            if plugin_id not in self.records:
                raise RuntimeError("Installed plugin failed manager validation")
            self.logger(f"Installed plugin: {plugin_id}")
            return self.records[plugin_id]
        except Exception:
            if staging.exists(): shutil.rmtree(staging, ignore_errors=True)
            if target.exists() and plugin_id not in self.records:
                shutil.rmtree(target, ignore_errors=True)
            raise

    @staticmethod
    def _version_tuple(value):
        parts = str(value).split(".")
        if not parts or len(parts) > 4 or any(not p.isdigit() for p in parts):
            raise ValueError("Plugin versions must use numeric dot-separated versions")
        return tuple(int(p) for p in parts)

    def update_plugin(self, source_folder):
        """Atomically replace an installed plugin with a newer, trusted signed build."""
        source = Path(source_folder).expanduser().resolve()
        verification = verify_plugin_folder(source, self.trusted_publishers)
        if verification["status"] != "trusted":
            raise PermissionError("Updates require a valid signature from a trusted publisher: " +
                                  verification["status"] + " — " + verification["detail"])
        manifest_path = source / "plugin.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("Update package must contain a regular plugin.json")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Plugin manifest must be a JSON object")
        plugin_id = str(data.get("id", ""))
        if not PLUGIN_ID_RE.fullmatch(plugin_id) or plugin_id not in self.records:
            raise KeyError("Update package does not match an installed plugin")
        current = self.records[plugin_id]
        if verification["fingerprint"] != current.publisher_fingerprint:
            raise PermissionError("Publisher key changed; key rotation requires a separate explicit trust workflow")
        new_version = str(data.get("version", ""))
        if self._version_tuple(new_version) <= self._version_tuple(current.version):
            raise ValueError("Update version must be newer than the installed version")
        entry = str(data.get("entrypoint", "plugin.py"))
        if Path(entry).name != entry or not entry.endswith(".py") or not (source / entry).is_file():
            raise ValueError("Update package has an invalid entrypoint")
        permissions = data.get("permissions", [])
        if not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions):
            raise ValueError("Plugin permissions must be a list of strings")
        unknown = set(permissions) - ALLOWED_PERMISSIONS
        if unknown:
            raise ValueError("Unknown permission(s): " + ", ".join(sorted(unknown)))
        for item in source.rglob("*"):
            if item.is_symlink():
                raise ValueError("Update package may not contain symbolic links")
        target = self.plugin_dir / plugin_id
        staging = self.plugin_dir / (".update-" + uuid.uuid4().hex)
        backup = self.plugin_dir / (".rollback-" + uuid.uuid4().hex)
        shutil.copytree(source, staging)
        try:
            staged = verify_plugin_folder(staging, self.trusted_publishers)
            if staged["status"] != "trusted" or staged["fingerprint"] != verification["fingerprint"]:
                raise PermissionError("Staged update failed signature verification")
            staged_data = json.loads((staging / "plugin.json").read_text(encoding="utf-8"))
            if str(staged_data.get("id", "")) != plugin_id or str(staged_data.get("version", "")) != new_version:
                raise RuntimeError("Update package changed while being staged")
            self.unload(plugin_id)
            os.replace(target, backup)
            try:
                os.replace(staging, target)
                self.scan()
                if plugin_id not in self.records or self.records[plugin_id].version != new_version:
                    raise RuntimeError("Updated plugin failed post-install validation")
            except Exception:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                os.replace(backup, target)
                self.scan()
                raise
            shutil.rmtree(backup, ignore_errors=True)
            self.logger(f"Updated plugin {plugin_id}: {current.version} -> {new_version}")
            return self.records[plugin_id]
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def uninstall(self, plugin_id, *, remove_data=False):
        """Remove plugin code; preserve user settings/data unless explicitly requested."""
        if not PLUGIN_ID_RE.fullmatch(str(plugin_id)):
            raise ValueError("Invalid plugin id")
        rec = self.records.get(plugin_id)
        target = self.plugin_dir / plugin_id
        if rec is None or not target.is_dir():
            raise KeyError(f"Plugin is not installed: {plugin_id}")
        self.unload(plugin_id)
        backup = self.plugin_dir / (".remove-" + uuid.uuid4().hex)
        previous = json.loads(json.dumps(self._state))
        os.replace(target, backup)
        try:
            if remove_data:
                self._state.pop(plugin_id, None)
            else:
                state = self._state.setdefault(plugin_id, {})
                state["enabled"] = False
            self._save_state()
        except Exception:
            self._state = previous
            os.replace(backup, target)
            self.scan()
            raise
        shutil.rmtree(backup)
        if remove_data:
            shutil.rmtree(self.plugin_data_dir(plugin_id), ignore_errors=True)
        self.scan()
        self.logger(f"Uninstalled plugin: {plugin_id}")

    def scan(self):
        found = {}
        for manifest_path in self.plugin_dir.glob("*/plugin.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                pid = str(data.get("id", manifest_path.parent.name))
                if not PLUGIN_ID_RE.fullmatch(pid) or pid in found: raise ValueError("Invalid or duplicate plugin id")
                entry = str(data.get("entrypoint", "plugin.py"))
                if Path(entry).name != entry or not entry.endswith(".py"): raise ValueError("Entrypoint must be a Python file in plugin folder")
                perms = tuple(sorted(set(data.get("permissions", []))))
                unknown = set(perms) - ALLOWED_PERMISSIONS
                if unknown: raise ValueError("Unknown permission(s): " + ", ".join(sorted(unknown)))
                previous = self.records.get(pid)
                found[pid] = PluginRecord(pid, str(data.get("name", pid))[:100], str(data.get("version", "0.0.0"))[:40],
                    str(data.get("description", ""))[:500], manifest_path.parent, entry, perms,
                    bool(self._state.get(pid, {}).get("enabled", False)),
                    loaded=pid in self._workers,
                    error=previous.error if previous else "",
                    signature_status=(verification := verify_plugin_folder(manifest_path.parent, self.trusted_publishers))["status"],
                    publisher_fingerprint=verification["fingerprint"])
            except Exception as exc: self.logger(f"Skipped {manifest_path}: {exc}")
        self.records = found
        return list(found.values())

    def set_enabled(self, plugin_id, enabled):
        rec = self.records[plugin_id]
        previous = bool(rec.enabled)
        rec.enabled = bool(enabled)
        self._state.setdefault(plugin_id, {})["enabled"] = rec.enabled
        try:
            self._save_state()
        except Exception:
            rec.enabled = previous
            self._state.setdefault(plugin_id, {})["enabled"] = previous
            raise
        if not rec.enabled: self.unload(plugin_id)

    def load(self, plugin_id, *, allow_untrusted=False):
        rec = self.records[plugin_id]
        if not rec.enabled: raise RuntimeError("Enable this plugin before loading it")
        verification = verify_plugin_folder(rec.folder, self.trusted_publishers)
        rec.signature_status = verification["status"]
        rec.publisher_fingerprint = verification["fingerprint"]
        if verification["status"] == "invalid":
            raise PermissionError("Plugin signature verification failed: " + verification["detail"])
        if verification["status"] != "trusted" and not allow_untrusted:
            raise PermissionError("Plugin publisher is not trusted (" + verification["status"] +
                "). Trust the publisher or explicitly allow this plugin.")
        if rec.loaded: return
        if not (rec.folder / rec.entrypoint).is_file(): raise FileNotFoundError(f"Plugin entrypoint not found: {rec.entrypoint}")
        worker = _Worker(rec, self.logger, self.notifier)
        try:
            worker.start()
            self._workers[plugin_id] = worker
            rec.loaded, rec.error = True, ""
            self.logger(f"Started isolated worker: {rec.name} v{rec.version}")
        except Exception as exc:
            worker.stop()
            rec.error, rec.loaded = f"{type(exc).__name__}: {exc}", False
            raise

    def unload(self, plugin_id):
        worker = self._workers.pop(plugin_id, None)
        if worker: worker.stop()
        if plugin_id in self.records: self.records[plugin_id].loaded = False

    def emit(self, event_name, **payload):
        if event_name not in ALLOWED_EVENTS: return
        for pid, worker in tuple(self._workers.items()):
            try:
                worker.emit(event_name, payload)
                if worker.process and worker.process.poll() is not None: raise RuntimeError("Worker exited unexpectedly")
            except Exception as exc:
                if pid in self.records: self.records[pid].error = f"Worker error: {type(exc).__name__}: {exc}"
                self.logger(f"Stopping faulty plugin worker {pid}: {exc}")
                self.unload(pid)

    def shutdown(self):
        for pid in tuple(self._workers): self.unload(pid)

class PluginManagerDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("FDMX Plugin Manager")
        self.resize(650, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Plugins run in separate processes. This is crash isolation, not an OS sandbox; plugins retain your user-account permissions."))
        self.items = QListWidget(); layout.addWidget(self.items, 1)
        self.details = QTextEdit(); self.details.setReadOnly(True); self.details.setMaximumHeight(110); layout.addWidget(self.details)
        buttons = QHBoxLayout()
        self.scan_button, self.enable_button = QPushButton("Refresh"), QPushButton("Enable")
        self.load_button, self.disable_button = QPushButton("Load"), QPushButton("Disable")
        self.install_button, self.uninstall_button = QPushButton("Install Folder"), QPushButton("Uninstall")
        self.trust_button = QPushButton("Trust Publisher")
        self.close_button = QPushButton("Close")
        for button in (self.scan_button, self.install_button, self.enable_button, self.load_button, self.disable_button, self.trust_button, self.uninstall_button): buttons.addWidget(button)
        buttons.addStretch(1); buttons.addWidget(self.close_button); layout.addLayout(buttons)
        self.scan_button.clicked.connect(self.refresh)
        self.install_button.clicked.connect(self._install_plugin)
        self.uninstall_button.clicked.connect(self._uninstall_plugin)
        self.trust_button.clicked.connect(self._trust_selected_publisher)
        self.enable_button.clicked.connect(lambda: self._set_enabled(True))
        self.disable_button.clicked.connect(lambda: self._set_enabled(False))
        self.load_button.clicked.connect(self._load_selected)
        self.close_button.clicked.connect(self.accept)
        self.items.currentRowChanged.connect(self._show_details)
        self.refresh()

    def _selected(self):
        item = self.items.currentItem()
        return item.data(256) if item else None

    def refresh(self):
        self.manager.scan(); self.items.clear()
        for rec in sorted(self.manager.records.values(), key=lambda r: r.name.lower()):
            state = "Running" if rec.loaded else ("Enabled" if rec.enabled else "Disabled")
            item = QListWidgetItem(f"{rec.name}  v{rec.version}  [{state}]")
            item.setData(256, rec.plugin_id); self.items.addItem(item)
        if self.items.count(): self.items.setCurrentRow(0)
        else: self.details.setPlainText("No plugins found. Add a plugin folder containing plugin.json and its Python entrypoint.")

    def _show_details(self, _row):
        pid = self._selected(); rec = self.manager.records.get(pid) if pid else None
        if not rec: self.details.clear(); return
        self.details.setPlainText(f"{rec.description}\nID: {rec.plugin_id}\nPermissions: {', '.join(rec.permissions) or 'none'}\nStatus: {'Running' if rec.loaded else ('Enabled' if rec.enabled else 'Disabled')}\nSignature: {rec.signature_status}\nPublisher fingerprint: {rec.publisher_fingerprint or '—'}\nError: {rec.error or 'None'}")

    def _install_plugin(self):
        folder = QFileDialog.getExistingDirectory(self, "Select plugin folder")
        if not folder: return
        try:
            verification = verify_plugin_folder(folder, self.manager.trusted_publishers)
            if verification["status"] != "trusted":
                answer = QMessageBox.warning(self, "Untrusted plugin",
                    "Signature status: " + verification["status"] + "\n" + verification["detail"] +
                    "\n\nInstalling an untrusted plugin can execute unsafe code. Continue?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes: return
                rec = self.manager.install_plugin(folder, allow_untrusted=True)
            else:
                rec = self.manager.install_plugin(folder)
            self.refresh()
            QMessageBox.information(self, "Plugin installed", f"{rec.name} v{rec.version} installed and remains disabled until enabled.")
        except Exception as exc:
            QMessageBox.warning(self, "Plugin installation failed", str(exc))

    def _uninstall_plugin(self):
        pid = self._selected()
        if not pid: return
        answer = QMessageBox.question(
            self, "Uninstall plugin",
            "Remove this plugin's code? Its settings and plugin data will be preserved.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes: return
        try:
            self.manager.uninstall(pid, remove_data=False)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Plugin uninstall failed", str(exc))

    def _set_enabled(self, enabled):
        pid = self._selected()
        if not pid: return
        try: self.manager.set_enabled(pid, enabled); self.refresh()
        except Exception as exc: QMessageBox.warning(self, "Plugin Manager", str(exc))

    def _trust_selected_publisher(self):
        pid = self._selected()
        if not pid: return
        rec = self.manager.records[pid]
        if rec.signature_status != "unknown_publisher":
            QMessageBox.information(self, "Publisher trust", "Only a valid signature from an unknown publisher can be trusted.")
            return
        answer = QMessageBox.warning(self, "Trust publisher",
            "Trust this publisher on this computer?\nFingerprint:\n" + rec.publisher_fingerprint +
            "\n\nVerify this fingerprint through a separate trusted channel first.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes: return
        try:
            fingerprint = self.manager.trust_plugin_publisher(pid)
            self.refresh()
            QMessageBox.information(self, "Publisher trusted", "Trusted publisher: " + fingerprint)
        except Exception as exc:
            QMessageBox.warning(self, "Trust publisher failed", str(exc))

    def _load_selected(self):
        pid = self._selected()
        if not pid: return
        rec = self.manager.records[pid]
        try:
            if rec.signature_status != "trusted":
                answer = QMessageBox.warning(self, "Untrusted plugin",
                    "Signature status: " + rec.signature_status +
                    "\nThis plugin can execute code with your user-account permissions. Load anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes: return
                self.manager.load(pid, allow_untrusted=True)
            else:
                self.manager.load(pid)
            self.refresh()
        except Exception as exc: QMessageBox.warning(self, "Plugin load failed", str(exc))
