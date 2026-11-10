"""Cross-platform tests for the FDMX isolated plugin worker SDK."""
import json
import tempfile
import time
import unittest
import sys
from pathlib import Path

from fdmx_plugin_sdk import PluginManager, _build_worker_command
from fdmx_plugin_host import WorkerAPI

class PluginWorkerPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "plugin"
        self.folder.mkdir()
        self.host = self.root / "fdmx_plugin_host.py"
        self.host.write_text("# worker host", encoding="utf-8")
        from types import SimpleNamespace
        self.record = SimpleNamespace(folder=self.folder, entrypoint="plugin.py",
                                      plugin_id="packaging_test", permissions=("app.log",))

    def tearDown(self):
        self.temp.cleanup()

    def test_source_mode_uses_python_host_script(self):
        command = _build_worker_command(self.record, self.host, frozen=False,
                                        executable="python-test")
        self.assertEqual(command[:3], ["python-test", "-u", str(self.host)])
        self.assertEqual(command[3:], [str(self.folder), "plugin.py", "packaging_test", '["app.log"]'])

    def test_frozen_mode_uses_companion_worker_next_to_app(self):
        worker = self.root / "fdmx_plugin_worker.exe"
        worker.write_bytes(b"test executable placeholder")
        command = _build_worker_command(self.record, self.host, frozen=True,
                                        executable=str(self.root / "FDMX.exe"),
                                        platform="win32")
        self.assertEqual(Path(command[0]), worker.resolve())
        self.assertEqual(command[1], str(self.folder))

    def test_frozen_mode_does_not_require_python_host_script(self):
        worker = self.root / "fdmx_plugin_worker"
        worker.write_bytes(b"test executable placeholder")
        self.host.unlink()
        command = _build_worker_command(self.record, self.host, frozen=True,
                                        executable=str(self.root / "FDMX"),
                                        platform="linux")
        self.assertEqual(Path(command[0]), worker.resolve())

    def test_frozen_mode_checks_bundle_directory(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        worker = bundle / "fdmx_plugin_worker"
        worker.write_bytes(b"test executable placeholder")
        command = _build_worker_command(self.record, self.host, frozen=True,
                                        executable=str(self.root / "FDMX"),
                                        bundle_dir=str(bundle), platform="linux")
        self.assertEqual(command[0], str(worker))

    def test_frozen_mode_reports_missing_worker_clearly(self):
        with self.assertRaisesRegex(FileNotFoundError, "Packaged plugin worker"):
            _build_worker_command(self.record, self.host, frozen=True,
                                  executable=str(self.root / "FDMX.exe"),
                                  platform="win32")


class PluginSDKTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plugin_root = self.root / ".fdmx" / "plugins"
        self.plugin_root.mkdir(parents=True)
        self.logs, self.notifications = [], []
        self.manager = PluginManager(self.plugin_root, logger=self.logs.append,
            notifier=lambda title, message: self.notifications.append((title, message)))

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def add_plugin(self, plugin_id="test_plugin", source=None, permissions=None):
        folder = self.plugin_root / plugin_id
        folder.mkdir(parents=True, exist_ok=True)
        manifest = {"id": plugin_id, "name": "Test Plugin", "version": "1.0.0",
            "entrypoint": "plugin.py", "permissions": permissions if permissions is not None
            else ["app.events", "app.log", "ui.notifications"]}
        (folder / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "plugin.py").write_text(source if source is not None else
            "def register(api):\n"
            "    api.on('app.started', lambda event: api.log('event:' + event.get('version', '?')))\n"
            "    api.on('download.completed', lambda event: api.notify('Done', event.get('name', 'file')))\n",
            encoding="utf-8")
        return folder

    def enable_and_load(self, plugin_id="test_plugin"):
        self.manager.scan()
        self.manager.set_enabled(plugin_id, True)
        self.manager.load(plugin_id)

    def wait_for(self, predicate, timeout=4.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(): return True
            time.sleep(0.03)
        return bool(predicate())

    def test_scan_does_not_auto_enable_plugins(self):
        self.add_plugin()
        records = self.manager.scan()
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].enabled)
        with self.assertRaisesRegex(RuntimeError, "Enable"):
            self.manager.load("test_plugin")

    def test_worker_receives_events_and_rpc_logging(self):
        self.add_plugin()
        self.enable_and_load()
        self.manager.emit("app.started", version="test")
        self.assertTrue(self.wait_for(lambda: any("event:test" in item for item in self.logs)))
        self.assertTrue(self.manager.records["test_plugin"].loaded)

    def test_worker_notification_rpc(self):
        self.add_plugin()
        self.enable_and_load()
        self.manager.emit("download.completed", name="report.zip")
        self.assertTrue(self.wait_for(lambda: ("Done", "report.zip") in self.notifications))

    def test_refresh_preserves_running_state(self):
        self.add_plugin()
        self.enable_and_load()
        self.manager.scan()
        self.assertTrue(self.manager.records["test_plugin"].loaded)

    def test_disable_stops_worker(self):
        self.add_plugin()
        self.enable_and_load()
        process = self.manager._workers["test_plugin"].process
        self.manager.set_enabled("test_plugin", False)
        self.assertFalse(self.manager.records["test_plugin"].loaded)
        self.assertIsNotNone(process.poll())

    def test_startup_exception_is_reported(self):
        self.add_plugin(source="raise RuntimeError('intentional startup failure')\n")
        self.manager.scan()
        self.manager.set_enabled("test_plugin", True)
        with self.assertRaisesRegex(RuntimeError, "intentional startup failure"):
            self.manager.load("test_plugin")
        self.assertFalse(self.manager.records["test_plugin"].loaded)
        self.assertIn("intentional startup failure", self.manager.records["test_plugin"].error)

    def test_sdk_permission_is_checked_before_rpc(self):
        api = WorkerAPI("permission_test", {"app.events"})
        with self.assertRaises(PermissionError): api.log("denied")
        with self.assertRaises(PermissionError): api.notify("title", "message")
        with self.assertRaises(ValueError): api.on("unsupported.event", lambda event: None)

    def test_oversized_event_stops_worker(self):
        self.add_plugin()
        self.enable_and_load()
        self.manager.emit("app.started", payload="x" * (1024 * 1024))
        self.assertFalse(self.manager.records["test_plugin"].loaded)
        self.assertIn("Worker error", self.manager.records["test_plugin"].error)

    def test_install_plugin_from_folder_and_keep_disabled(self):
        source = self.root / "incoming_plugin"
        source.mkdir()
        (source / "plugin.json").write_text(json.dumps({
            "id": "installed_plugin", "name": "Installed", "version": "1.2",
            "entrypoint": "plugin.py", "permissions": ["app.log"]
        }), encoding="utf-8")
        (source / "plugin.py").write_text("def register(api):\\n    api.log('installed')\\n", encoding="utf-8")
        rec = self.manager.install_plugin(source)
        self.assertEqual(rec.plugin_id, "installed_plugin")
        self.assertFalse(rec.enabled)
        self.assertTrue((self.plugin_root / "installed_plugin" / "plugin.py").is_file())

    def test_install_rejects_invalid_manifest_without_partial_folder(self):
        source = self.root / "bad_plugin"
        source.mkdir()
        (source / "plugin.json").write_text('{"id":"bad","permissions":["root.access"]}', encoding="utf-8")
        (source / "plugin.py").write_text("def register(api): pass\\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unknown permission"):
            self.manager.install_plugin(source)
        self.assertFalse((self.plugin_root / "bad" ).exists())

    def test_uninstall_preserves_settings_and_data_by_default(self):
        self.add_plugin()
        self.manager.scan()
        self.manager.set_plugin_settings("test_plugin", {"theme": "dark", "count": 3})
        data_dir = self.manager.plugin_data_dir("test_plugin")
        data_dir.mkdir(parents=True)
        (data_dir / "user.db").write_text("keep", encoding="utf-8")
        self.manager.uninstall("test_plugin")
        self.assertNotIn("test_plugin", self.manager.records)
        self.assertEqual(self.manager.get_plugin_settings("test_plugin"), {"theme": "dark", "count": 3})
        self.assertEqual((data_dir / "user.db").read_text(encoding="utf-8"), "keep")
        self.assertFalse(self.manager._state["test_plugin"]["enabled"])

    def test_uninstall_can_explicitly_remove_settings_and_data(self):
        self.add_plugin()
        self.manager.scan()
        self.manager.set_plugin_settings("test_plugin", {"token_label": "sample"})
        data_dir = self.manager.plugin_data_dir("test_plugin")
        data_dir.mkdir(parents=True)
        (data_dir / "cache.bin").write_bytes(b"cache")
        self.manager.uninstall("test_plugin", remove_data=True)
        self.assertNotIn("test_plugin", self.manager._state)
        self.assertFalse(data_dir.exists())

    def test_failed_uninstall_restores_plugin_folder_and_state(self):
        self.add_plugin()
        self.manager.scan()
        original_save = self.manager._save_state
        self.manager._save_state = lambda: (_ for _ in ()).throw(OSError("simulated state write failure"))
        try:
            with self.assertRaisesRegex(OSError, "simulated"):
                self.manager.uninstall("test_plugin")
        finally:
            self.manager._save_state = original_save
        self.assertTrue((self.plugin_root / "test_plugin" / "plugin.json").is_file())
        self.assertIn("test_plugin", self.manager.scan())

    def test_shutdown_callback_runs(self):
        marker = self.root / "shutdown.marker"
        source = ("from pathlib import Path\n"
            "def register(api):\n    api.log('ready')\n"
            "def shutdown():\n"
            f"    Path({str(marker)!r}).write_text('stopped', encoding='utf-8')\n")
        self.add_plugin(source=source)
        self.enable_and_load()
        self.manager.shutdown()
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.read_text(encoding="utf-8"), "stopped")

if __name__ == "__main__":
    unittest.main(verbosity=2)
