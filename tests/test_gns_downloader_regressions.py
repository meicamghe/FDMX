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
        self.assertIn('APP_VERSION = "6.37"', SOURCE)

    def test_theme_studio_and_plugin_manager_are_removed(self):
        self.assertNotIn("Theme Studio", SOURCE)
        self.assertNotIn("Plugin Manager", SOURCE)
        self.assertNotIn("PluginManager", SOURCE)
        self.assertNotIn("plugin_manager", SOURCE)

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
