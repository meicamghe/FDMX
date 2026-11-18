"""Regression checks for ephemeral browser-authenticated GitHub downloads."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")


class BrowserSessionArtifactTests(unittest.TestCase):
    def test_source_compiles(self):
        compile(SOURCE, "FDMX_v6_50.py", "exec")

    def test_browser_bridge_accepts_original_and_resolved_urls(self):
        self.assertIn("browser_download_requested = Signal(str, str)", SOURCE)
        self.assertIn('payload.get("resolved_url", "")', SOURCE)
        self.assertIn("window.browser_download_requested.emit(url, resolved_url)", SOURCE)

    def test_temporary_signed_url_is_used_for_metadata_and_transfer(self):
        self.assertIn('FileInfoWorker(task.get("browser_resolved_url") or task["url"]', SOURCE)
        self.assertIn('task.get("browser_resolved_url") or task["url"], task["folder"]', SOURCE)

    def test_temporary_signed_url_is_not_written_to_task_snapshots(self):
        block = SOURCE[SOURCE.index("def save_tasks"):SOURCE.index("def load_history")]
        self.assertIn('"url"', block)
        self.assertNotIn('"browser_resolved_url"', block)

    def test_history_keeps_the_original_github_artifact_page(self):
        block = SOURCE[SOURCE.index("def save_history_entry"):SOURCE.index("def load_preferences")]
        self.assertIn('"url": task["url"]', block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
