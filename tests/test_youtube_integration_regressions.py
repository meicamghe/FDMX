"""Offline regression tests for YouTube download integration.

These tests do not contact YouTube or require yt-dlp/FFmpeg.
"""
import ast
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "FDMX_v6_43.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")


def load_output_resolver():
    tree = ast.parse(SOURCE)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_resolve_youtube_output_path"
    )
    namespace = {"os": os}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
    return namespace[node.name]


class YouTubeIntegrationRegressionTests(unittest.TestCase):
    def test_application_source_compiles(self):
        compile(SOURCE, str(SOURCE_PATH), "exec")

    def test_video_prefers_best_video_and_audio_with_mp4_merge(self):
        self.assertIn('"format": "bestvideo+bestaudio/best"', SOURCE)
        self.assertIn('"merge_output_format": "mp4"', SOURCE)

    def test_audio_selects_best_available_audio_without_forcing_conversion(self):
        self.assertIn('"format": "bestvideo+bestaudio/best" if self.media_type == "video" else "bestaudio[ext=m4a]/bestaudio"', SOURCE)

    def test_final_postprocessed_filepath_is_preferred(self):
        resolve = load_output_resolver()
        with tempfile.TemporaryDirectory() as folder:
            merged = Path(folder) / "merged.mp4"
            intermediate = Path(folder) / "video.f137.mp4"
            merged.write_bytes(b"merged")
            intermediate.write_bytes(b"video")
            downloader = type("Downloader", (), {
                "prepare_filename": lambda self, info: str(intermediate)
            })()
            result = resolve(
                {"filepath": str(merged), "requested_downloads": [{"filepath": str(intermediate)}]},
                downloader,
            )
            self.assertEqual(result, str(merged))

    def test_requested_download_filepath_is_used_when_final_filepath_is_absent(self):
        resolve = load_output_resolver()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "audio.m4a"
            output.write_bytes(b"audio")
            downloader = type("Downloader", (), {
                "prepare_filename": lambda self, info: str(Path(folder) / "missing.mp4")
            })()
            result = resolve(
                {"requested_downloads": [{"filepath": str(output)}]},
                downloader,
            )
            self.assertEqual(result, str(output))

    def test_prepare_filename_remains_a_fallback(self):
        resolve = load_output_resolver()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "fallback.webm"
            output.write_bytes(b"data")
            downloader = type("Downloader", (), {
                "prepare_filename": lambda self, info: str(output)
            })()
            result = resolve({}, downloader)
            self.assertEqual(result, str(output))

    def test_worker_checks_the_resolved_output_exists(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker_source = SOURCE[worker_start:worker_end]
        self.assertIn("_resolve_youtube_output_path(info, downloader)", worker_source)
        self.assertIn("os.path.isfile(path)", worker_source)
        self.assertIn("self.completed.emit(path)", worker_source)


    def test_video_download_requires_and_configures_ffmpeg(self):
        self.assertIn("def _youtube_ffmpeg_executable():", SOURCE)
        self.assertIn('options["ffmpeg_location"] = ffmpeg_executable', SOURCE)
        self.assertIn("Best-quality YouTube video downloads need FFmpeg.", SOURCE)

    def test_audio_download_does_not_require_ffmpeg(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker_source = SOURCE[worker_start:worker_end]
        self.assertIn('if self.media_type == "video":', worker_source)
        self.assertIn('"bestaudio[ext=m4a]/bestaudio"', worker_source)

    def test_youtube_tasks_keep_media_type_when_persisted_and_restored(self):
        self.assertIn('"media_type": entry.get("media_type", "video")', SOURCE)
        self.assertIn('"category", "kind", "media_type", "scheduled_at"', SOURCE)

    def test_pause_cancel_and_progress_hooks_are_connected(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker_source = SOURCE[worker_start:worker_end]
        self.assertIn('"progress_hooks": [self._progress_hook]', worker_source)
        self.assertIn("self.pause_event.wait(0.2)", worker_source)
        self.assertIn("self.cancel_event.is_set()", worker_source)


if __name__ == "__main__":
    unittest.main()
