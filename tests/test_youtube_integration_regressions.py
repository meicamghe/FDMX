"""Offline regression tests for YouTube download integration.

These tests do not contact YouTube or require yt-dlp/FFmpeg.
"""
import ast
import os
from pathlib import Path
import tempfile
import unittest
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "FDMX_v6_48.py"
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


def load_proxy_normalizer():
    tree = ast.parse(SOURCE)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "normalize_proxy_url")
    namespace = {"urllib": urllib}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
    return namespace[node.name]


class YouTubeIntegrationRegressionTests(unittest.TestCase):
    def test_safe_int_handles_null_and_corrupt_saved_values(self):
        tree = ast.parse(SOURCE)
        node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_safe_int")
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        safe_int = namespace["_safe_int"]
        self.assertEqual(safe_int(None), 0)
        self.assertEqual(safe_int(""), 0)
        self.assertEqual(safe_int("3"), 3)
        self.assertEqual(safe_int("broken", 7), 7)
        self.assertEqual(safe_int(None, 5), 5)

    def test_task_restore_uses_safe_integer_conversion(self):
        self.assertIn('"retry_attempts": _safe_int(entry.get("retry_attempts"), 0)', SOURCE)
        self.assertIn('"parts_count": max(0, _safe_int(entry.get("parts_count"), 0))', SOURCE)

    def test_application_source_compiles(self):
        compile(SOURCE, str(SOURCE_PATH), "exec")

    def test_update_checker_uses_the_existing_help_menu_action(self):
        self.assertNotIn("Test update checker", SOURCE)
        self.assertNotIn("self.update_check_btn", SOURCE)
        self.assertIn('help_menu.addAction("Check for updates…", self.check_for_updates)', SOURCE)
        self.assertIn('APP_VERSION = "6.48"', SOURCE)

    def test_disabled_context_menu_actions_are_visibly_distinguished(self):
        self.assertIn('QMenu::item:disabled { color: #888888; }', SOURCE)
        self.assertIn('action.setEnabled(available)', SOURCE)
        self.assertNotIn('(unavailable)', SOURCE)
        self.assertIn('set_action_available(start_action, status == "Queued")', SOURCE)
        self.assertIn('set_action_available(resume_action, status == "Paused")', SOURCE)
        self.assertIn('set_action_available(cancel_action, active)', SOURCE)
        self.assertIn('set_action_available(retry_action, status in ("Failed", "Canceled"))', SOURCE)

    def test_proxy_normalizer_accepts_supported_schemes(self):
        normalize = load_proxy_normalizer()
        for scheme in ("http", "https", "socks4", "socks4a", "socks5", "socks5h"):
            with self.subTest(scheme=scheme):
                self.assertEqual(normalize(f"{scheme}://127.0.0.1:1080"), f"{scheme}://127.0.0.1:1080")

    def test_proxy_normalizer_rejects_invalid_proxy(self):
        normalize = load_proxy_normalizer()
        with self.assertRaises(ValueError):
            normalize("ftp://127.0.0.1:21")
        with self.assertRaises(ValueError):
            normalize("socks5://127.0.0.1")

    def test_regular_download_worker_accepts_proxy_configuration(self):
        start = SOURCE.index("class DownloadWorker")
        end = SOURCE.index("class TorrentWorker", start)
        worker = SOURCE[start:end]
        self.assertIn("proxy_url=\"\"", SOURCE[SOURCE.index("class DownloadWorker"):SOURCE.index("class YouTubeDownloadWorker")])
        self.assertIn("open_url_with_proxy(req, timeout=30", worker)
        self.assertIn("self.proxy_url = normalize_proxy_url(proxy_url)", worker)

    def test_socks_dns_mode_distinguishes_local_and_remote_resolution(self):
        self.assertIn('rdns=(scheme in ("socks4a", "socks5h"))', SOURCE)

    def test_socks_proxy_is_scoped_to_the_current_worker_thread(self):
        self.assertIn("_PROXY_THREAD_STATE = threading.local()", SOURCE)
        self.assertIn("with thread_proxy(proxy_url):", SOURCE)
        self.assertIn("socket.create_connection = _proxy_aware_create_connection", SOURCE)

    def test_youtube_worker_passes_proxy_to_ytdlp(self):
        start = SOURCE.index("class YouTubeDownloadWorker")
        end = SOURCE.index("class GitHubUpdateDownloadWorker", start)
        worker = SOURCE[start:end]
        self.assertIn('options["proxy"] = self.proxy_url', worker)
        self.assertIn("self.proxy_url = normalize_proxy_url(proxy_url)", worker)

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


    def test_existing_file_choice_offers_replace_new_copy_and_open(self):
        self.assertIn('box.addButton("Replace existing file"', SOURCE)
        self.assertIn('box.addButton("Save as new file"', SOURCE)
        self.assertIn('box.addButton("Open existing file"', SOURCE)
        self.assertIn('task["destination_path"] = existing_path if choice == "overwrite"', SOURCE)
        self.assertIn('self.destination_path or unique_path(self.folder, filename)', SOURCE)

    def test_youtube_cancel_releases_worker_waiting_for_file_conflict(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker = SOURCE[worker_start:worker_end]
        cancel_start = worker.index("    def cancel(self):")
        cancel_end = worker.index("    def _progress_hook", cancel_start)
        cancel_method = worker[cancel_start:cancel_end]
        self.assertIn('self._conflict_action = "cancel"', cancel_method)
        self.assertIn("self._conflict_event.set()", cancel_method)
        wait_block = worker[worker.index("self._conflict_event.wait()"):]
        self.assertIn("if self.cancel_event.is_set():", wait_block)
        self.assertIn("self.canceled.emit()", wait_block)

    def test_youtube_checks_existing_file_before_download_and_waits_for_choice(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker = SOURCE[worker_start:worker_end]
        self.assertIn('self.file_conflict.emit(existing_path)', worker)
        self.assertIn('self._conflict_event.wait()', worker)
        self.assertIn('downloader.params["overwrites"] = True', worker)
        self.assertIn('downloader.params["outtmpl"] = candidate_template', worker)
        self.assertIn('self.existing_file.emit(existing_path)', worker)

    def test_duplicate_detection_uses_source_url_not_shared_filename(self):
        tree = ast.parse(SOURCE)
        nodes = [
            node for node in tree.body
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in ("_normalized_download_url", "_is_active_duplicate_task", "_is_duplicate_download")
            ) or (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "_ACTIVE_DUPLICATE_STATUSES" for target in node.targets)
            )
        ]
        namespace = {"urllib": urllib}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        is_duplicate = namespace["_is_duplicate_download"]
        active = {"url": "https://mirror-a.example/FDMX_v6_46.py", "name": "FDMX_v6_46.py", "status": "Downloading"}
        same_name_other_source = {"url": "https://mirror-b.example/FDMX_v6_46.py", "name": "FDMX_v6_46.py", "status": "Downloading"}
        same_source = {"url": "https://mirror-a.example/FDMX_v6_46.py", "name": "renamed.py", "status": "Queued"}
        completed = {"url": "https://mirror-a.example/FDMX_v6_46.py", "name": "FDMX_v6_46.py", "status": "Completed"}
        self.assertFalse(is_duplicate(same_name_other_source, active["url"]))
        self.assertTrue(is_duplicate(same_source, active["url"]))
        self.assertFalse(is_duplicate(completed, active["url"]))
        self.assertTrue(is_duplicate(
            {"url": "HTTPS://MIRROR-A.EXAMPLE/FDMX_v6_46.py#download", "status": "Downloading"},
            active["url"],
        ))

    def test_youtube_duplicate_detection_preserves_media_type(self):
        tree = ast.parse(SOURCE)
        nodes = [
            node for node in tree.body
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in ("_normalized_download_url", "_is_active_duplicate_task", "_is_duplicate_download")
            ) or (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "_ACTIVE_DUPLICATE_STATUSES" for target in node.targets)
            )
        ]
        namespace = {"urllib": urllib}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        is_duplicate = namespace["_is_duplicate_download"]
        existing = {"url": "https://www.youtube.com/watch?v=abc", "kind": "youtube", "media_type": "video", "status": "Queued"}
        self.assertTrue(is_duplicate(existing, existing["url"], "youtube", "video"))
        self.assertFalse(is_duplicate(existing, existing["url"], "youtube", "audio"))

    def test_only_active_tasks_block_duplicate_downloads(self):
        self.assertIn("def _is_active_duplicate_task(task):", SOURCE)
        self.assertIn("def _is_duplicate_download(existing, url, kind=", SOURCE)
        self.assertIn('"Queued", "Ready", "Checking metadata", "Checking server", "Downloading"', SOURCE)
        self.assertIn('"Paused", "Retrying", "Canceling", "Seeding"', SOURCE)
        self.assertNotIn("same_target =", SOURCE)

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
