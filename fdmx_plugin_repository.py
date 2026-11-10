"""HTTPS plugin repository client with archive integrity and safe extraction."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_BYTES = 250 * 1024 * 1024
MAX_FILES = 5000


class PluginRepositoryError(RuntimeError):
    pass


class PluginRepository:
    """Minimal read-only repository client; packages are trusted only after SDK signature checks."""

    def __init__(self, catalog_url, *, timeout=20):
        self.catalog_url = str(catalog_url)
        self.timeout = timeout
        if not self.catalog_url.startswith("https://"):
            raise ValueError("Plugin repository catalog must use HTTPS")

    def _fetch(self, url, limit):
        if not str(url).startswith("https://"):
            raise PluginRepositoryError("Repository resources must use HTTPS")
        request = urllib.request.Request(url, headers={"User-Agent": "FDMX-PluginRepository/1.0"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > limit:
                raise PluginRepositoryError("Repository resource exceeds size limit")
            data = response.read(limit + 1)
        if len(data) > limit:
            raise PluginRepositoryError("Repository resource exceeds size limit")
        return data

    def list_plugins(self):
        try:
            raw = self._fetch(self.catalog_url, MAX_CATALOG_BYTES)
            catalog = json.loads(raw.decode("utf-8"))
        except PluginRepositoryError:
            raise
        except Exception as exc:
            raise PluginRepositoryError("Unable to read plugin catalog: " + str(exc)) from exc
        if not isinstance(catalog, dict) or catalog.get("format") != "FDMX-PLUGIN-REPOSITORY-V1":
            raise PluginRepositoryError("Unsupported plugin catalog format")
        entries = catalog.get("plugins")
        if not isinstance(entries, list) or len(entries) > 1000:
            raise PluginRepositoryError("Invalid plugin catalog entries")
        seen = set()
        for item in entries:
            if not isinstance(item, dict):
                raise PluginRepositoryError("Invalid plugin catalog entry")
            pid, version = item.get("id"), item.get("version")
            if not isinstance(pid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", pid):
                raise PluginRepositoryError("Invalid plugin id in catalog")
            if pid in seen:
                raise PluginRepositoryError("Duplicate plugin id in catalog")
            seen.add(pid)
            if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+){0,3}", version):
                raise PluginRepositoryError("Invalid plugin version in catalog")
            if not isinstance(item.get("archive_url"), str) or not item["archive_url"].startswith("https://"):
                raise PluginRepositoryError("Plugin archive must use HTTPS")
            if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", item["sha256"]):
                raise PluginRepositoryError("Invalid archive SHA-256")
        return entries

    def download_package(self, entry, destination):
        if not isinstance(entry, dict):
            raise TypeError("Repository entry must be an object")
        archive = self._fetch(entry["archive_url"], MAX_ARCHIVE_BYTES)
        digest = hashlib.sha256(archive).hexdigest()
        if digest.lower() != entry["sha256"].lower():
            raise PluginRepositoryError("Plugin archive SHA-256 mismatch")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(archive)) as bundle:
                infos = bundle.infolist()
                if len(infos) > MAX_FILES:
                    raise PluginRepositoryError("Plugin archive contains too many files")
                total = 0
                seen_paths = set()
                for info in infos:
                    name = info.filename.replace("\\", "/")
                    path = PurePosixPath(name)
                    mode = (info.external_attr >> 16) & 0xFFFF
                    normalized = path.as_posix().casefold()
                    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in path.parts[0]:
                        raise PluginRepositoryError("Unsafe path in plugin archive")
                    if normalized in seen_paths:
                        raise PluginRepositoryError("Duplicate path in plugin archive")
                    seen_paths.add(normalized)
                    if (mode & 0o170000) == 0o120000:
                        raise PluginRepositoryError("Symbolic links are not allowed in plugin archives")
                    total += info.file_size
                    if total > MAX_EXTRACTED_BYTES:
                        raise PluginRepositoryError("Expanded plugin archive exceeds size limit")
                    target = destination.joinpath(*path.parts)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.open(info) as src, target.open("wb") as dst:
                            remaining = info.file_size
                            while remaining:
                                chunk = src.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    raise PluginRepositoryError("Truncated plugin archive member")
                                dst.write(chunk)
                                remaining -= len(chunk)
                if not (destination / "plugin.json").is_file():
                    raise PluginRepositoryError("Archive must contain plugin.json at its root")
        except zipfile.BadZipFile as exc:
            raise PluginRepositoryError("Invalid ZIP plugin archive") from exc
        return destination

    def update(self, manager, plugin_id):
        entries = {item["id"]: item for item in self.list_plugins()}
        if plugin_id not in entries:
            raise KeyError("Plugin is not listed in this repository")
        entry = entries[plugin_id]
        with tempfile.TemporaryDirectory(prefix="fdmx-plugin-update-") as temp:
            package = self.download_package(entry, temp)
            manifest = json.loads((package / "plugin.json").read_text(encoding="utf-8"))
            if str(manifest.get("id")) != plugin_id or str(manifest.get("version")) != entry["version"]:
                raise PluginRepositoryError("Catalog metadata does not match signed plugin manifest")
            record = manager.update_plugin(package)
            return record
