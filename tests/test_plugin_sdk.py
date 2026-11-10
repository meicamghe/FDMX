"""Cross-platform tests for the FDMX isolated plugin worker SDK."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from fdmx_plugin_sdk import PluginManager
from fdmx_plugin_host import WorkerAPI

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
