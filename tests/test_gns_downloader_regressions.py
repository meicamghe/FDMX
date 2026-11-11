"""Static regression checks for the branded desktop app and download cancellation."""
from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "FDMX_v6_36.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


class AppRegressionTests(unittest.TestCase):
    def test_application_source_compiles(self):
        compile(SOURCE, str(SOURCE_PATH), "exec")

    def test_product_brand_and_version(self):
        self.assertIn('APP_NAME = "GNS Downloader"', SOURCE)
        self.assertIn('APP_VERSION = "6.39"', SOURCE)

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
        self.assertIn('QDesktopServices.openUrl(QUrl.fromLocalFile', SOURCE)

    def test_adaptive_speed_probe_selects_and_persists_safe_part_layout(self):
        self.assertIn('def _measure_initial_speed(self, temp_folder, total):', SOURCE)
        self.assertIn('def _choose_part_count(self, total, measured_speed):', SOURCE)
        self.assertIn('self.parts_configured.emit(parts_count, measured_speed)', SOURCE)
        self.assertIn('"parts.json"', SOURCE)
        self.assertIn('parts_count = int(candidate["count"])', SOURCE)
        self.assertIn('Legacy fixed-eight fragments must keep their original byte-range map.', SOURCE)
        self.assertIn('"parts_count", "measured_speed"', SOURCE)

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
