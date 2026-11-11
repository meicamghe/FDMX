"""Static regression checks for the branded desktop app and download cancellation."""
from pathlib import Path
import ast
import re
import urllib.error
import urllib.request
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "FDMX_v6_36.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


class AppRegressionTests(unittest.TestCase):
    def test_application_source_compiles(self):
        compile(SOURCE, str(SOURCE_PATH), "exec")

    def test_product_brand_and_version(self):
        self.assertIn('APP_NAME = "GNS Downloader"', SOURCE)
        self.assertIn('APP_VERSION = "6.40.1"', SOURCE)

    def test_theme_studio_and_plugin_manager_are_removed(self):
        self.assertNotIn("Theme Studio", SOURCE)
        self.assertNotIn("Plugin Manager", SOURCE)
        self.assertNotIn("PluginManager", SOURCE)
        self.assertNotIn("plugin_manager", SOURCE)

    def test_post_download_action_is_configured_per_download(self):
        self.assertIn('After this download finishes:', SOURCE)
        self.assertIn('def run_task_post_action(self, task):', SOURCE)
        self.assertIn('self.run_task_post_action(task)', SOURCE)
        self.assertNotIn('After all downloads finish:', SOURCE)
        self.assertNotIn('check_after_download_action', SOURCE)

    def test_disabled_buttons_have_a_distinct_visual_state(self):
        self.assertIn('QPushButton:disabled', SOURCE)
        self.assertIn('border: 1px dashed #aab4c2', SOURCE)

    def test_completed_download_window_switches_to_open_and_close(self):
        self.assertIn('self.open_btn = QPushButton("Open")', SOURCE)
        self.assertIn('self.close_btn = QPushButton("Close")', SOURCE)
        self.assertIn('for button in (self.start_btn, self.pause_btn, self.resume_btn, self.cancel_btn, self.retry_btn):', SOURCE)
        self.assertIn('button.setVisible(not completed)', SOURCE)
        self.assertIn('self.open_btn.setVisible(completed)', SOURCE)
        self.assertIn('self.open_btn.clicked.connect(self.open_downloaded_file)', SOURCE)
        self.assertIn('self.post_action_enabled.setEnabled(not completed)', SOURCE)
        self.assertIn('QDesktopServices.openUrl(QUrl.fromLocalFile', SOURCE)

    def test_adaptive_speed_probe_selects_and_persists_safe_part_layout(self):
        self.assertIn('def _measure_initial_speed(self, temp_folder, total):', SOURCE)
        self.assertIn('def _choose_part_count(self, total, measured_speed):', SOURCE)
        self.assertIn('self.parts_configured.emit(parts_count, measured_speed)', SOURCE)
        self.assertIn('"parts.json"', SOURCE)
        self.assertIn('candidate_count = int(candidate.get("count", 0))', SOURCE)
        self.assertIn('Legacy fixed-eight fragments must keep their original byte-range map.', SOURCE)
        self.assertIn('"parts_count", "measured_speed"', SOURCE)

    def test_https_uses_verified_certifi_ca_bundle(self):
        self.assertIn("import certifi", SOURCE)
        self.assertIn("ssl.create_default_context(cafile=bundle)", SOURCE)
        self.assertIn("urllib.request.HTTPSHandler(context=SSL_CONTEXT)", SOURCE)
        self.assertIn("urllib.request.install_opener(build_url_opener())", SOURCE)
        self.assertIn("build_url_opener(handler)", SOURCE)
        self.assertNotIn("_create_unverified_context", SOURCE)

    def test_download_probe_falls_back_to_plain_get(self):
        self.assertIn("def request_headers(self, start=None, end=None):", SOURCE)
        self.assertIn('"Accept-Encoding": "identity"', SOURCE)
        self.assertIn('"Accept": "*/*"', SOURCE)
        self.assertIn("def probe_download(self):", SOURCE)
        self.assertIn("for use_range in (True, False):", SOURCE)
        self.assertIn("Server rejected both Range and ordinary GET requests", SOURCE)
        self.assertIn("class RangeNotSupportedError(RuntimeError):", SOURCE)

    def test_range_failure_falls_back_to_single_stream(self):
        self.assertIn("except RangeNotSupportedError:", SOURCE)
        self.assertIn('self.state.emit("Range unavailable; using single connection")', SOURCE)
        self.assertIn("self.download_single(destination)", SOURCE)
        self.assertIn("Server rejected HTTP Range with status", SOURCE)

    def test_probe_retries_with_plain_get_after_range_is_rejected(self):
        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "DownloadWorker"
        )
        method = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "probe_download"
        )
        namespace = {
            "re": re,
            "urllib": urllib,
            "get_filename": lambda response: "DWA-131_DRIVER_1.21_WIN.ZIP",
        }
        module = ast.Module(body=[method], type_ignores=[])
        exec(compile(module, "<probe_download>", "exec"), namespace)

        class FakeResponse:
            status = 200
            headers = {
                "Content-Length": "17775053",
                "Content-Disposition": 'attachment; filename="DWA-131_DRIVER_1.21_WIN.ZIP"',
            }

            def read(self, size):
                return b"x"

            def close(self):
                pass

        class FakeWorker:
            cancel_event = SimpleNamespace(is_set=lambda: False)
            pause_event = SimpleNamespace(is_set=lambda: True)

            def __init__(self):
                self.requests = []

            def request(self, start=None, end=None):
                self.requests.append((start, end))
                if start is not None:
                    raise urllib.error.HTTPError(
                        "https://example.invalid/driver.zip",
                        403, "Forbidden", {}, None
                    )
                return FakeResponse()

            def get_response_socket(self, response):
                return None

            def register_socket(self, sock):
                pass

            def unregister_socket(self, sock):
                pass

            def wait_if_paused(self):
                pass

        worker = FakeWorker()
        result = namespace["probe_download"](worker)
        self.assertEqual(
            result,
            ("DWA-131_DRIVER_1.21_WIN.ZIP", False, 17775053),
        )
        self.assertEqual(worker.requests, [(0, 0), (None, None)])

    def test_adaptive_part_count_thresholds(self):
        tree = ast.parse(SOURCE)
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_choose_part_count"
        )
        namespace = {"CONNECTIONS": 8}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "<adaptive>", "exec"), namespace)
        Worker = type("Worker", (), {"_choose_part_count": namespace["_choose_part_count"]})
        worker = Worker()
        mib = 1024 * 1024
        self.assertEqual(worker._choose_part_count(1 * mib, 8 * mib), 1)
        self.assertEqual(worker._choose_part_count(20 * mib, 128 * 1024), 1)
        self.assertEqual(worker._choose_part_count(20 * mib, 512 * 1024), 2)
        self.assertEqual(worker._choose_part_count(20 * mib, 2 * mib), 4)
        self.assertEqual(worker._choose_part_count(20 * mib, 8 * mib), 8)


    def test_about_credits_and_github_updater(self):
        self.assertIn("Created by MeysamGNS", SOURCE)
        self.assertIn("Developed with assistance from ChatGPT", SOURCE)
        self.assertIn("class GitHubUpdateWorker(QThread):", SOURCE)
        self.assertIn("https://api.github.com/repos/meicamghe/FDMX/releases/latest", SOURCE)
        self.assertIn('expected_digest.startswith("sha256:")', SOURCE)
        self.assertIn('help_menu.addAction("Check for updates…", self.check_for_updates)', SOURCE)


    def test_updater_distinguishes_installed_and_portable_builds(self):
        self.assertIn("def _is_installed_windows_build():", SOURCE)
        self.assertIn('os.path.commonpath([root, executable]) == root', SOURCE)
        self.assertIn('if not _is_installed_windows_build():', SOURCE)
        self.assertIn("Portable ZIP for a portable or source-based copy", SOURCE)

    def test_ubuntu_yaru_theme_is_selected_only_on_linux(self):
        self.assertIn('self.theme_combo.addItem("Ubuntu Yaru", "ubuntu_yaru")', SOURCE)
        self.assertIn('"ubuntu_yaru": ("#f6f5f4", "#ffffff", "#e8e6e3"', SOURCE)
        self.assertIn('default_theme = "ubuntu_yaru" if sys.platform.startswith("linux") else "fluent"', SOURCE)
        self.assertIn('"Ubuntu", "Cantarell", "Noto Sans"', SOURCE)

    def test_cancel_handles_tasks_without_live_download_workers(self):
        tree = ast.parse(SOURCE)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("cancel_task", methods)
        cancel_source = ast.get_source_segment(SOURCE, methods["cancel_task"])
        self.assertIn("metadata_worker", cancel_source)
        self.assertIn('"Canceling"', cancel_source)
        self.assertIn('"Canceled"', cancel_source)

    def test_failed_metadata_is_not_marked_ready(self):
        tree = ast.parse(SOURCE)
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        handler = ast.get_source_segment(SOURCE, methods["on_file_info_ready"])
        self.assertIn('info.get("error")', handler)
        self.assertIn('"Failed"', handler)

    def test_paused_tasks_do_not_trigger_recovery_prompt_every_launch(self):
        self.assertIn('interrupted_states = ("Downloading", "Checking server", "Retrying", "Seeding")', SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
