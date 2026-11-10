"""Tests for HTTPS plugin repository validation and signed atomic updates."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fdmx_plugin_sdk import PluginManager, sign_plugin_folder
from fdmx_plugin_repository import PluginRepository, PluginRepositoryError


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugins = self.root / "plugins"
        self.plugins.mkdir()
        self.manager = PluginManager(self.plugins)
        self.key = Ed25519PrivateKey.generate()
        self.private = self.key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.public = self.key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        self.manager.trust_publisher(self.public)

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def make_package(self, version):
        folder = self.root / ("pkg-" + version)
        folder.mkdir()
        (folder / "plugin.json").write_text(json.dumps({
            "id": "repo_plugin", "name": "Repository Plugin", "version": version,
            "entrypoint": "plugin.py", "permissions": ["app.log"]
        }), encoding="utf-8")
        (folder / "plugin.py").write_text("def register(api):\n    api.log('v" + version + "')\n", encoding="utf-8")
        sign_plugin_folder(folder, self.private)
        return folder

    def archive(self, folder):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in folder.iterdir():
                zf.write(path, path.name)
        return output.getvalue()

    def fake_repository(self, archive, *, expected=None):
        digest = expected or hashlib.sha256(archive).hexdigest()
        catalog = json.dumps({
            "format": "FDMX-PLUGIN-REPOSITORY-V1",
            "plugins": [{"id": "repo_plugin", "version": "2.0",
                         "archive_url": "https://repo.example/plugins/repo_plugin-2.0.zip",
                         "sha256": digest}]
        }).encode()
        repo = PluginRepository("https://repo.example/catalog.json")
        repo._fetch = lambda url, limit: catalog if url.endswith("catalog.json") else archive
        return repo

    def test_repository_update_installs_newer_trusted_signed_version(self):
        old = self.make_package("1.0")
        self.manager.install_plugin(old)
        new = self.make_package("2.0")
        record = self.fake_repository(self.archive(new)).update(self.manager, "repo_plugin")
        self.assertEqual(record.version, "2.0")
        self.assertEqual(record.signature_status, "trusted")
        self.assertEqual((self.plugins / "repo_plugin" / "plugin.json").is_file(), True)

    def test_archive_digest_mismatch_does_not_change_installed_plugin(self):
        old = self.make_package("1.0")
        self.manager.install_plugin(old)
        new = self.make_package("2.0")
        with self.assertRaisesRegex(PluginRepositoryError, "SHA-256 mismatch"):
            self.fake_repository(self.archive(new), expected="0" * 64).update(self.manager, "repo_plugin")
        self.assertEqual(self.manager.records["repo_plugin"].version, "1.0")

    def test_untrusted_or_modified_signature_blocks_update(self):
        old = self.make_package("1.0")
        self.manager.install_plugin(old)
        new = self.make_package("2.0")
        (new / "plugin.py").write_text("def register(api): pass\n", encoding="utf-8")
        with self.assertRaises(PermissionError):
            self.manager.update_plugin(new)
        self.assertEqual(self.manager.records["repo_plugin"].version, "1.0")

    def test_archive_path_traversal_is_rejected(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../outside.txt", "bad")
        repo = PluginRepository("https://repo.example/catalog.json")
        repo._fetch = lambda url, limit: archive.getvalue()
        with self.assertRaisesRegex(PluginRepositoryError, "Unsafe path"):
            repo.download_package({"archive_url": "https://repo.example/plugin.zip",
                                   "sha256": hashlib.sha256(archive.getvalue()).hexdigest()},
                                  self.root / "extract")

    def test_update_keeps_history_and_signed_rollback_restores_previous_version(self):
        old = self.make_package("1.0")
        self.manager.install_plugin(old)
        new = self.make_package("2.0")
        self.fake_repository(self.archive(new)).update(self.manager, "repo_plugin")
        history = self.manager.list_plugin_versions("repo_plugin")
        self.assertEqual([item["version"] for item in history], ["1.0"])
        record = self.manager.rollback_plugin("repo_plugin", history[0]["folder"])
        self.assertEqual(record.version, "1.0")
        self.assertEqual(record.signature_status, "trusted")
        remaining = self.manager.list_plugin_versions("repo_plugin")
        self.assertEqual([item["version"] for item in remaining], ["2.0"])

    def test_rollback_rejects_modified_historical_package(self):
        old = self.make_package("1.0")
        self.manager.install_plugin(old)
        new = self.make_package("2.0")
        self.fake_repository(self.archive(new)).update(self.manager, "repo_plugin")
        history = self.manager.list_plugin_versions("repo_plugin")
        (history[0]["folder"] / "plugin.py").write_text("def register(api): pass\\n", encoding="utf-8")
        with self.assertRaises(PermissionError):
            self.manager.rollback_plugin("repo_plugin", history[0]["folder"])
        self.assertEqual(self.manager.records["repo_plugin"].version, "2.0")

    def test_repository_requires_https(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            PluginRepository("http://repo.example/catalog.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
