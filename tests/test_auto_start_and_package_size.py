"""Regression checks for one-click download startup and release size limits."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")
WINDOWS_WORKFLOW = (ROOT / ".github/workflows/build-fdmx-windows.yml").read_text(encoding="utf-8")


class AutoStartAndPackageSizeTests(unittest.TestCase):
    def test_application_source_compiles(self):
        compile(SOURCE, "FDMX_v6_50.py", "exec")

    def test_metadata_ready_queues_and_starts_without_second_click(self):
        tree = ast.parse(SOURCE)
        fdmx = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FDMX")
        method = next(node for node in fdmx.body if isinstance(node, ast.FunctionDef) and node.name == "on_file_info_ready")
        calls = [
            node.func.attr for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"
        ]
        self.assertIn("start_queue", calls)
        self.assertIn('task["status"] = "Queued"', SOURCE)
        self.assertIn("Starting download…", SOURCE)
        self.assertNotIn("Press Start to download.", SOURCE)

    def test_youtube_video_has_single_file_fallback_without_ffmpeg(self):
        self.assertIn('options["format"] = "best"', SOURCE)
        self.assertIn('options.pop("merge_output_format", None)', SOURCE)
        self.assertIn('return shutil.which("ffmpeg")', SOURCE)
        self.assertNotIn("import imageio_ffmpeg", SOURCE)

    def test_windows_release_assets_are_limited_to_50_mib(self):
        self.assertIn("$limit = 50MB", WINDOWS_WORKFLOW)
        self.assertIn("GNS-Downloader-Setup-6.50.exe", WINDOWS_WORKFLOW)
        self.assertIn("GNS-Downloader-Portable-v6.50-Windows-x64.zip", WINDOWS_WORKFLOW)
        self.assertIn("if ($file.Length -gt $limit)", WINDOWS_WORKFLOW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
