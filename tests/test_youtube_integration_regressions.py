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
SOURCE_PATH = ROOT / "FDMX_v6_50.py"
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
        self.assertIn('APP_VERSION = "6.50"', SOURCE)

    def test_update_checker_selects_highest_stable_release_independent_of_api_order(self):
        tree = ast.parse(SOURCE)
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("_version_key", "_highest_stable_release")
        ]
        namespace = {"re": __import__("re")}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        select = namespace["_highest_stable_release"]
        releases = [
            {"tag_name": "v6.47", "draft": False, "prerelease": False},
            {"tag_name": "v6.50", "draft": False, "prerelease": False},
            {"tag_name": "v6.99-rc1", "draft": False, "prerelease": True},
            {"tag_name": "v6.99-rc2", "draft": False, "prerelease": False},
            {"tag_name": "v6.50.1.2", "draft": False, "prerelease": False},
            {"tag_name": "v7.00", "draft": True, "prerelease": False},
            {"tag_name": "release-not-numbered", "draft": False, "prerelease": False},
        ]
        self.assertEqual(select(releases)["tag_name"], "v6.50")
        self.assertEqual(select(list(reversed(releases)))["tag_name"], "v6.50")
        self.assertIsNone(select([]))

    def test_update_version_comparison_handles_patch_and_missing_components(self):
        tree = ast.parse(SOURCE)
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef) and item.name == "_version_key"
        )
        namespace = {"re": __import__("re")}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        version_key = namespace["_version_key"]
        self.assertGreater(version_key("v6.50.10"), version_key("6.50.9"))
        self.assertEqual(version_key("6.50"), version_key("6.50.0"))

    def test_update_installer_is_removed_if_setup_launch_fails(self):
        start = SOURCE.index("    def on_update_downloaded(self, installer_path):")
        end = SOURCE.index("    def set_filter", start)
        handler = SOURCE[start:end]
        launch = handler.index("subprocess.Popen([installer_path], close_fds=True)")
        failure = handler[launch:]
        self.assertIn("except OSError as exc:", failure)
        self.assertIn("os.remove(installer_path)", failure)
        self.assertIn('self.status.setText("Update installer could not be started.")', failure)

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
        with self.assertRaises(ValueError):
            normalize("http://proxy.example:not-a-port")
        with self.assertRaises(ValueError):
            normalize("socks5://proxy.example:1080/path")
        with self.assertRaises(ValueError):
            normalize("socks5://proxy.example:1080?mode=remote")
        self.assertEqual(
            normalize("http://user:pass@[::1]:8080/"),
            "http://user:pass@[::1]:8080",
        )

    def test_regular_download_worker_accepts_proxy_configuration(self):
        start = SOURCE.index("class DownloadWorker")
        end = SOURCE.index("class TorrentWorker", start)
        worker = SOURCE[start:end]
        self.assertIn("proxy_url=\"\"", SOURCE[SOURCE.index("class DownloadWorker"):SOURCE.index("class YouTubeDownloadWorker")])
        self.assertIn("open_url_with_proxy(req, timeout=30", worker)
        self.assertIn("self.proxy_url = normalize_proxy_url(proxy_url)", worker)

    def test_socks_dns_mode_distinguishes_local_and_remote_resolution(self):
        self.assertIn('rdns=(scheme in ("socks4a", "socks5h"))', SOURCE)

    def test_socks_connection_applies_remote_dns_credentials_and_timeout(self):
        import socket
        import threading
        import types

        tree = ast.parse(SOURCE)
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_proxy_aware_create_connection"
        )
        calls = {}

        class FakeSocksSocket:
            def set_proxy(self, *args, **kwargs):
                calls["proxy"] = (args, kwargs)

            def settimeout(self, value):
                calls["timeout"] = value

            def bind(self, value):
                calls["source_address"] = value

            def connect(self, value):
                calls["address"] = value

        fake_socks = types.SimpleNamespace(
            SOCKS4=4, SOCKS5=5, socksocket=FakeSocksSocket
        )
        state = threading.local()
        state.url = "socks5h://user%40name:p%3Ass@proxy.example:1080"
        namespace = {
            "getattr": getattr,
            "threading": threading,
            "_PROXY_THREAD_STATE": state,
            "_ORIGINAL_CREATE_CONNECTION": lambda *a, **k: None,
            "socket": socket,
            "urllib": urllib,
            "__builtins__": __builtins__,
        }
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "socks":
                return fake_socks
            return original_import(name, *args, **kwargs)

        namespace["__builtins__"] = dict(vars(__builtins__)) if not isinstance(__builtins__, dict) else dict(__builtins__)
        namespace["__builtins__"]["__import__"] = fake_import
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        connect = namespace["_proxy_aware_create_connection"]
        connect(("origin.example", 443), timeout=17, source_address=("127.0.0.1", 0))
        args, kwargs = calls["proxy"]
        self.assertEqual(args[:3], (5, "proxy.example", 1080))
        self.assertTrue(kwargs["rdns"])
        self.assertEqual(kwargs["username"], "user@name")
        self.assertEqual(kwargs["password"], "p:ss")
        self.assertEqual(calls["timeout"], 17)
        self.assertEqual(calls["source_address"], ("127.0.0.1", 0))
        self.assertEqual(calls["address"], ("origin.example", 443))

    def test_socks_connection_uses_local_dns_for_socks4(self):
        import socket
        import threading
        import types

        tree = ast.parse(SOURCE)
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_proxy_aware_create_connection"
        )
        calls = {}

        class FakeSocksSocket:
            def set_proxy(self, *args, **kwargs):
                calls["proxy"] = (args, kwargs)

            def settimeout(self, value):
                pass

            def bind(self, value):
                pass

            def connect(self, value):
                pass

        fake_socks = types.SimpleNamespace(
            SOCKS4=4, SOCKS5=5, socksocket=FakeSocksSocket
        )
        state = threading.local()
        state.url = "socks4://proxy.example:1080"
        original_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "socks":
                return fake_socks
            return original_import(name, *args, **kwargs)

        builtins_map = dict(vars(__builtins__)) if not isinstance(__builtins__, dict) else dict(__builtins__)
        builtins_map["__import__"] = fake_import
        namespace = {
            "_PROXY_THREAD_STATE": state,
            "_ORIGINAL_CREATE_CONNECTION": lambda *a, **k: None,
            "socket": socket,
            "urllib": urllib,
            "__builtins__": builtins_map,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE_PATH), "exec"), namespace)
        namespace["_proxy_aware_create_connection"](("origin.example", 443))
        args, kwargs = calls["proxy"]
        self.assertEqual(args[0], 4)
        self.assertFalse(kwargs["rdns"])

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

    def test_regular_http_worker_cancel_does_not_use_youtube_conflict_state(self):
        start = SOURCE.index("class DownloadWorker")
        end = SOURCE.index("class TorrentWorker", start)
        worker = SOURCE[start:end]
        cancel_start = worker.index("    def cancel(self):")
        cancel_end = worker.index("    def ", cancel_start + 5)
        cancel_method = worker[cancel_start:cancel_end]
        self.assertNotIn("_conflict_action", cancel_method)
        self.assertNotIn("_conflict_event", cancel_method)

    def test_youtube_cancel_method_releases_conflict_wait_at_runtime(self):
        import threading

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        cancel_node = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "cancel"
        )
        namespace = {}
        exec(
            compile(ast.Module(body=[cancel_node], type_ignores=[]), str(SOURCE_PATH), "exec"),
            namespace,
        )

        class WorkerStub:
            def __init__(self):
                self.cancel_event = threading.Event()
                self.pause_event = threading.Event()
                self._conflict_event = threading.Event()
                self._conflict_action = "overwrite"

        worker = WorkerStub()
        namespace["cancel"].__get__(worker, WorkerStub)()
        self.assertTrue(worker.cancel_event.is_set())
        self.assertTrue(worker.pause_event.is_set())
        self.assertTrue(worker._conflict_event.is_set())
        self.assertEqual(worker._conflict_action, "cancel")

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
        self.assertIn('self.file_conflict.emit(self.task_id, existing_path)', worker)
        self.assertIn('self._conflict_event.wait()', worker)
        self.assertIn('downloader.params["overwrites"] = True', worker)
        self.assertIn('downloader.params["outtmpl"] = candidate_template', worker)
        self.assertIn('self.existing_file.emit(self.task_id, existing_path)', worker)

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


    def test_youtube_download_keeps_resumable_partial_files_and_bounded_timeout(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker_source = SOURCE[worker_start:worker_end]
        self.assertIn('"continuedl": True', worker_source)
        self.assertIn('"nopart": False', worker_source)
        self.assertIn('"overwrites": False', worker_source)
        self.assertIn('"socket_timeout": 30', worker_source)
        self.assertIn('"progress_hooks": [self._progress_hook]', worker_source)
        # The worker must not delete yt-dlp's .part files on cancellation:
        # they are the resume point for a subsequent attempt.
        self.assertNotIn("os.remove(", worker_source)
        self.assertNotIn("shutil.rmtree(", worker_source)

    def test_update_download_rejects_unsupported_or_malformed_release_digest(self):
        start = SOURCE.index("class GitHubUpdateDownloadWorker")
        end = SOURCE.index("def is_youtube_url", start)
        worker = SOURCE[start:end]
        self.assertIn('algorithm.lower() != "sha256"', worker)
        self.assertIn('not re.fullmatch(r"[0-9a-fA-F]{64}", expected)', worker)
        self.assertIn("if self.expected_digest:", worker)
        self.assertIn("unsupported or malformed installer digest", worker)

    def test_update_download_cancel_interrupts_active_socket(self):
        import socket
        import threading

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GitHubUpdateDownloadWorker"
        )
        methods = {
            node.name: node for node in worker_class.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("cancel", "_interrupt_response")
        }
        namespace = {"socket": socket}
        exec(
            compile(ast.Module(body=[methods["_interrupt_response"], methods["cancel"]], type_ignores=[]), str(SOURCE_PATH), "exec"),
            namespace,
        )

        class SocketStub:
            def __init__(self):
                self.shutdown_mode = None

            def shutdown(self, how):
                self.shutdown_mode = how

        class ResponseStub:
            def __init__(self):
                self.socket = SocketStub()
                self.fp = type("Stream", (), {
                    "raw": type("Raw", (), {"_sock": self.socket})()
                })()
                self.closed = False

            def close(self):
                self.closed = True

        class WorkerStub:
            def __init__(self):
                self.cancel_event = threading.Event()
                self._response_lock = threading.Lock()
                self._active_response = ResponseStub()
                self._interrupt_response = namespace["_interrupt_response"].__get__(self, WorkerStub)

        worker = WorkerStub()
        response = worker._active_response
        namespace["cancel"].__get__(worker, WorkerStub)()
        self.assertTrue(worker.cancel_event.is_set())
        self.assertEqual(response.socket.shutdown_mode, socket.SHUT_RDWR)
        self.assertTrue(response.closed)

    def test_update_download_treats_network_close_after_cancel_as_canceled(self):
        start = SOURCE.index("class GitHubUpdateDownloadWorker")
        end = SOURCE.index("def is_youtube_url", start)
        worker = SOURCE[start:end]
        self.assertIn("self._active_response = response", worker)
        self.assertIn("self._interrupt_response(response)", worker)
        self.assertIn("sock.shutdown(socket.SHUT_RDWR)", worker)
        self.assertIn("response.close()", worker)
        self.assertIn("if self.cancel_event.is_set():", worker)
        self.assertIn("self.canceled.emit()", worker)
        self.assertIn("self._active_response = None", worker)


    def test_linux_compatibility_launcher_uses_current_source(self):
        launcher = (ROOT / "ubuntu.py").read_text(encoding="utf-8")
        self.assertIn('with_name("FDMX_v6_50.py")', launcher)
        self.assertNotIn('with_name("FDMX_v6_36.py")', launcher)


    def test_youtube_cancel_after_metadata_does_not_start_transfer(self):
        start = SOURCE.index("class YouTubeDownloadWorker")
        end = SOURCE.index("class GitHubUpdateDownloadWorker", start)
        worker = SOURCE[start:end]
        metadata = worker.index("info = downloader.extract_info(self.url, download=False)")
        transfer = worker.index("info = downloader.process_ie_result(info, download=True)")
        between = worker[metadata:transfer]
        self.assertIn("if self.cancel_event.is_set():", between)
        self.assertIn("self.canceled.emit()", between)
        self.assertIn("return", between)
        self.assertLess(metadata, transfer)


    def test_youtube_file_conflict_ui_handlers_are_qt_bound_connections(self):
        worker_start = SOURCE.index("class YouTubeDownloadWorker")
        worker_end = SOURCE.index("class GitHubUpdateDownloadWorker", worker_start)
        worker = SOURCE[worker_start:worker_end]
        self.assertIn("file_conflict = Signal(str, str)", worker)
        self.assertIn("existing_file = Signal(str, str)", worker)
        self.assertIn("self.file_conflict.emit(self.task_id, existing_path)", worker)
        self.assertIn("self.existing_file.emit(self.task_id, existing_path)", worker)
        self.assertIn("worker.file_conflict.connect(self.on_youtube_file_conflict)", SOURCE)
        self.assertIn("worker.existing_file.connect(self.on_youtube_existing_file)", SOURCE)
        self.assertNotIn("worker.file_conflict.connect(lambda", SOURCE)
        self.assertNotIn("worker.existing_file.connect(lambda", SOURCE)
        self.assertIn("def on_youtube_file_conflict(self, task_id, path):", SOURCE)


    def test_youtube_ui_handlers_are_explicit_qt_slots(self):
        self.assertIn("from PySide6.QtCore import QThread, Signal, Slot, Qt", SOURCE)
        self.assertIn("@Slot(str, str)\n    def on_youtube_file_conflict", SOURCE)
        self.assertIn("@Slot(str, str)\n    def on_youtube_existing_file", SOURCE)


    def test_youtube_run_cancellation_during_metadata_never_starts_transfer(self):
        import sys
        import threading
        import types

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        run_node = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        calls = {"extract": 0, "transfer": 0, "canceled": 0}

        class FakeDownloader:
            def __init__(self, options):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                calls["extract"] += 1
                self_owner.cancel_event.set()
                return {"id": "test-video"}

            def process_ie_result(self, info, download=False):
                calls["transfer"] += 1
                return info

            def prepare_filename(self, info):
                return os.path.join(self_owner.folder, "test-video.m4a")

        fake_module = types.SimpleNamespace(YoutubeDL=FakeDownloader)

        class SignalStub:
            def emit(self, *args):
                calls["canceled"] += 1

        class NoopSignal:
            def emit(self, *args):
                pass

        class WorkerStub:
            pass

        with tempfile.TemporaryDirectory() as folder:
            self_owner = WorkerStub()
            self_owner.url = "https://www.youtube.com/watch?v=test"
            self_owner.folder = folder
            self_owner.media_type = "audio"
            self_owner.proxy_url = ""
            self_owner.cancel_event = threading.Event()
            self_owner.state = NoopSignal()
            self_owner.canceled = SignalStub()
            self_owner.failed = NoopSignal()
            self_owner.progress = NoopSignal()
            self_owner._progress_hook = lambda data: None
            namespace = {
                "os": os,
                "time": __import__("time"),
                "_resolve_youtube_output_path": lambda info, downloader: "",
                "_youtube_ffmpeg_executable": lambda: "",
                "normalize_proxy_url": lambda value: value,
                "__builtins__": __builtins__,
            }
            exec(
                compile(ast.Module(body=[run_node], type_ignores=[]), str(SOURCE_PATH), "exec"),
                namespace,
            )
            previous = sys.modules.get("yt_dlp")
            sys.modules["yt_dlp"] = fake_module
            try:
                namespace["run"](self_owner)
            finally:
                if previous is None:
                    sys.modules.pop("yt_dlp", None)
                else:
                    sys.modules["yt_dlp"] = previous

        self.assertEqual(calls["extract"], 1)
        self.assertEqual(calls["transfer"], 0)
        self.assertEqual(calls["canceled"], 1)


    def test_youtube_run_cancel_during_existing_file_prompt_releases_worker(self):
        import sys
        import threading
        import types

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        run_node = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        calls = {"transfer": 0, "canceled": 0, "conflict": 0}

        class FakeDownloader:
            def __init__(self, options):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"id": "existing-video"}

            def process_ie_result(self, info, download=False):
                calls["transfer"] += 1
                return info

            def prepare_filename(self, info):
                return existing_path

        class NoopSignal:
            def emit(self, *args):
                pass

        class CancelSignal:
            def emit(self, *args):
                calls["canceled"] += 1

        class ConflictSignal:
            def emit(self, *args):
                calls["conflict"] += 1
                self_owner.cancel()

        class WorkerStub:
            def cancel(self):
                self.cancel_event.set()
                self.pause_event.set()
                self._conflict_action = "cancel"
                self._conflict_event.set()

        with tempfile.TemporaryDirectory() as folder:
            existing_path = os.path.join(folder, "existing.m4a")
            Path(existing_path).write_bytes(b"existing")
            self_owner = WorkerStub()
            self_owner.task_id = "test-task"
            self_owner.url = "https://www.youtube.com/watch?v=existing"
            self_owner.folder = folder
            self_owner.media_type = "audio"
            self_owner.proxy_url = ""
            self_owner.cancel_event = threading.Event()
            self_owner.pause_event = threading.Event()
            self_owner.pause_event.set()
            self_owner._conflict_event = threading.Event()
            self_owner._conflict_action = "cancel"
            self_owner.state = NoopSignal()
            self_owner.canceled = CancelSignal()
            self_owner.failed = NoopSignal()
            self_owner.progress = NoopSignal()
            self_owner.file_conflict = ConflictSignal()
            self_owner.existing_file = NoopSignal()
            self_owner._progress_hook = lambda data: None
            namespace = {
                "os": os,
                "time": __import__("time"),
                "_resolve_youtube_output_path": lambda info, downloader: "",
                "_youtube_ffmpeg_executable": lambda: "",
                "normalize_proxy_url": lambda value: value,
                "__builtins__": __builtins__,
            }
            exec(
                compile(ast.Module(body=[run_node], type_ignores=[]), str(SOURCE_PATH), "exec"),
                namespace,
            )
            fake_module = types.SimpleNamespace(YoutubeDL=FakeDownloader)
            previous = sys.modules.get("yt_dlp")
            sys.modules["yt_dlp"] = fake_module
            try:
                namespace["run"](self_owner)
            finally:
                if previous is None:
                    sys.modules.pop("yt_dlp", None)
                else:
                    sys.modules["yt_dlp"] = previous

        self.assertEqual(calls["conflict"], 1)
        self.assertEqual(calls["transfer"], 0)
        self.assertEqual(calls["canceled"], 1)


    def test_youtube_existing_file_choices_execute_expected_actions(self):
        import sys
        import threading
        import types

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        run_node = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )

        for action in ("overwrite", "new", "open"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as folder:
                existing_path = os.path.join(folder, "existing.m4a")
                Path(existing_path).write_bytes(b"existing")
                calls = {"conflict": 0, "existing": 0, "transfer": 0, "completed": [], "canceled": 0, "failed": 0, "state": 0, "progress": 0}
                downloader_instances = []

                class FakeDownloader:
                    def __init__(self, options):
                        self.params = options
                        downloader_instances.append(self)

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def extract_info(self, url, download=False):
                        return {"id": "existing-video"}

                    def prepare_filename(self, info):
                        return existing_path

                    def process_ie_result(self, info, download=False):
                        calls["transfer"] += 1
                        Path(output_path).write_bytes(b"downloaded")
                        return info

                class SignalStub:
                    def __init__(self, key):
                        self.key = key

                    def emit(self, *args):
                        if self.key == "completed":
                            calls[self.key].append(args[0])
                        else:
                            calls[self.key] += 1

                class ConflictSignal:
                    def emit(self, *args):
                        calls["conflict"] += 1
                        self_owner.resolve_file_conflict(action)

                class WorkerStub:
                    def resolve_file_conflict(self, selected):
                        self._conflict_action = selected
                        self._conflict_event.set()

                self_owner = WorkerStub()
                self_owner.task_id = "choice-test"
                self_owner.url = "https://www.youtube.com/watch?v=existing"
                self_owner.folder = folder
                self_owner.media_type = "audio"
                self_owner.proxy_url = ""
                self_owner.cancel_event = threading.Event()
                self_owner.pause_event = threading.Event()
                self_owner.pause_event.set()
                self_owner._conflict_event = threading.Event()
                self_owner._conflict_action = "cancel"
                self_owner.state = SignalStub("state")
                self_owner.canceled = SignalStub("canceled")
                self_owner.failed = SignalStub("failed")
                self_owner.completed = SignalStub("completed")
                self_owner.progress = SignalStub("progress")
                self_owner.file_conflict = ConflictSignal()
                self_owner.existing_file = SignalStub("existing")
                self_owner._progress_hook = lambda data: None

                output_path = (
                    os.path.join(folder, "existing (1).m4a")
                    if action == "new" else existing_path
                )
                namespace = {
                    "os": os,
                    "time": __import__("time"),
                    "_resolve_youtube_output_path": lambda info, downloader: output_path,
                    "_youtube_ffmpeg_executable": lambda: "",
                    "normalize_proxy_url": lambda value: value,
                    "__builtins__": __builtins__,
                }
                exec(
                    compile(ast.Module(body=[run_node], type_ignores=[]), str(SOURCE_PATH), "exec"),
                    namespace,
                )
                previous = sys.modules.get("yt_dlp")
                sys.modules["yt_dlp"] = types.SimpleNamespace(YoutubeDL=FakeDownloader)
                try:
                    namespace["run"](self_owner)
                finally:
                    if previous is None:
                        sys.modules.pop("yt_dlp", None)
                    else:
                        sys.modules["yt_dlp"] = previous

                self.assertEqual(calls["conflict"], 1)
                self.assertEqual(calls["canceled"], 0)
                self.assertEqual(calls["failed"], 0)
                self.assertEqual(len(downloader_instances), 1)
                params = downloader_instances[0].params

                if action == "open":
                    self.assertEqual(calls["transfer"], 0)
                    self.assertEqual(calls["existing"], 1)
                    self.assertEqual(calls["completed"], [existing_path])
                else:
                    self.assertEqual(calls["transfer"], 1)
                    self.assertEqual(calls["existing"], 0)
                    self.assertEqual(calls["completed"], [output_path])
                    if action == "overwrite":
                        self.assertIs(params["overwrites"], True)
                        self.assertIs(params["continuedl"], False)
                    else:
                        self.assertIn("existing (1).%(ext)s", params["outtmpl"])


    def test_youtube_cancel_during_transfer_preserves_partial_file_for_resume(self):
        import sys
        import threading
        import time
        import types

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        run_node = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        progress_hook_node = next(
            node for node in worker_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "_progress_hook"
        )
        calls = {"transfer": 0, "canceled": 0, "completed": 0, "failed": 0}

        class FakeDownloader:
            def __init__(self, options):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"id": "partial-transfer"}

            def prepare_filename(self, info):
                return final_path

            def process_ie_result(self, info, download=False):
                calls["transfer"] += 1
                Path(partial_path).write_bytes(b"partial download")
                self_owner.cancel_event.set()
                self.params["progress_hooks"][0]({
                    "status": "downloading",
                    "downloaded_bytes": len(b"partial download"),
                    "total_bytes": 100,
                })
                raise AssertionError("progress hook should cancel the transfer")

        class SignalCounter:
            def __init__(self, key):
                self.key = key

            def emit(self, *args):
                calls[self.key] += 1

        class NoopSignal:
            def emit(self, *args):
                pass

        class WorkerStub:
            pass

        with tempfile.TemporaryDirectory() as folder:
            final_path = os.path.join(folder, "partial-transfer.m4a")
            partial_path = final_path + ".part"
            self_owner = WorkerStub()
            self_owner.url = "https://www.youtube.com/watch?v=partial-transfer"
            self_owner.folder = folder
            self_owner.media_type = "audio"
            self_owner.proxy_url = ""
            self_owner.cancel_event = threading.Event()
            self_owner.pause_event = threading.Event()
            self_owner.pause_event.set()
            self_owner._last_downloaded = 0
            self_owner._last_time = time.monotonic()
            self_owner._speed = 0.0
            self_owner.state = NoopSignal()
            self_owner.canceled = SignalCounter("canceled")
            self_owner.completed = SignalCounter("completed")
            self_owner.failed = SignalCounter("failed")
            self_owner.progress = NoopSignal()
            namespace = {
                "os": os,
                "time": time,
                "_resolve_youtube_output_path": lambda info, downloader: final_path,
                "_youtube_ffmpeg_executable": lambda: "",
                "normalize_proxy_url": lambda value: value,
                "__builtins__": __builtins__,
            }
            exec(
                compile(
                    ast.Module(body=[run_node, progress_hook_node], type_ignores=[]),
                    str(SOURCE_PATH),
                    "exec",
                ),
                namespace,
            )
            self_owner._progress_hook = types.MethodType(
                namespace["_progress_hook"], self_owner
            )
            previous = sys.modules.get("yt_dlp")
            sys.modules["yt_dlp"] = types.SimpleNamespace(YoutubeDL=FakeDownloader)
            try:
                namespace["run"](self_owner)
            finally:
                if previous is None:
                    sys.modules.pop("yt_dlp", None)
                else:
                    sys.modules["yt_dlp"] = previous

            self.assertEqual(calls["transfer"], 1)
            self.assertEqual(calls["canceled"], 1)
            self.assertEqual(calls["completed"], 0)
            self.assertEqual(calls["failed"], 0)
            self.assertTrue(os.path.isfile(partial_path))
            self.assertEqual(Path(partial_path).read_bytes(), b"partial download")
            self.assertFalse(os.path.exists(final_path))


    def test_youtube_pause_holds_transfer_until_resumed(self):
        import sys
        import threading
        import time
        import types

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        methods = {
            node.name: node for node in worker_class.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("run", "_progress_hook")
        }
        calls = {"progress": 0, "completed": 0, "canceled": 0, "failed": 0}
        hook_entered = threading.Event()

        class FakeDownloader:
            def __init__(self, options):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"id": "paused-transfer"}

            def prepare_filename(self, info):
                return final_path

            def process_ie_result(self, info, download=False):
                hook_entered.set()
                self.params["progress_hooks"][0]({
                    "status": "downloading",
                    "downloaded_bytes": 25,
                    "total_bytes": 100,
                    "speed": 10,
                    "eta": 8,
                })
                Path(final_path).write_bytes(b"completed after resume")
                return info

        class SignalCounter:
            def __init__(self, key):
                self.key = key

            def emit(self, *args):
                calls[self.key] += 1

        class NoopSignal:
            def emit(self, *args):
                pass

        class WorkerStub:
            pass

        with tempfile.TemporaryDirectory() as folder:
            final_path = os.path.join(folder, "paused-transfer.m4a")
            self_owner = WorkerStub()
            self_owner.url = "https://www.youtube.com/watch?v=paused-transfer"
            self_owner.folder = folder
            self_owner.media_type = "audio"
            self_owner.proxy_url = ""
            self_owner.cancel_event = threading.Event()
            self_owner.pause_event = threading.Event()
            # Start paused; the real yt-dlp progress hook must block here.
            self_owner._last_downloaded = 0
            self_owner._last_time = time.monotonic()
            self_owner._speed = 0.0
            self_owner.state = NoopSignal()
            self_owner.progress = SignalCounter("progress")
            self_owner.completed = SignalCounter("completed")
            self_owner.canceled = SignalCounter("canceled")
            self_owner.failed = SignalCounter("failed")
            namespace = {
                "os": os,
                "time": time,
                "_resolve_youtube_output_path": lambda info, downloader: final_path,
                "_youtube_ffmpeg_executable": lambda: "",
                "normalize_proxy_url": lambda value: value,
                "__builtins__": __builtins__,
            }
            exec(
                compile(
                    ast.Module(body=[methods["run"], methods["_progress_hook"]], type_ignores=[]),
                    str(SOURCE_PATH),
                    "exec",
                ),
                namespace,
            )
            self_owner._progress_hook = types.MethodType(
                namespace["_progress_hook"], self_owner
            )
            previous = sys.modules.get("yt_dlp")
            sys.modules["yt_dlp"] = types.SimpleNamespace(YoutubeDL=FakeDownloader)
            worker_thread = threading.Thread(target=namespace["run"], args=(self_owner,))
            try:
                worker_thread.start()
                self.assertTrue(hook_entered.wait(2), "download never reached its progress hook")
                time.sleep(0.3)
                self.assertTrue(worker_thread.is_alive(), "paused transfer should remain blocked")
                self.assertEqual(calls["progress"], 0)
                self.assertFalse(os.path.exists(final_path))

                self_owner.pause_event.set()
                worker_thread.join(3)
                self.assertFalse(worker_thread.is_alive(), "transfer did not resume")
            finally:
                self_owner.pause_event.set()
                if worker_thread.is_alive():
                    worker_thread.join(3)
                if previous is None:
                    sys.modules.pop("yt_dlp", None)
                else:
                    sys.modules["yt_dlp"] = previous

            self.assertEqual(calls["progress"], 1)
            self.assertEqual(calls["completed"], 1)
            self.assertEqual(calls["canceled"], 0)
            self.assertEqual(calls["failed"], 0)
            self.assertTrue(os.path.isfile(final_path))


    def test_youtube_cancel_while_paused_releases_progress_hook(self):
        import sys
        import threading
        import time
        import types

        tree = ast.parse(SOURCE)
        worker_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "YouTubeDownloadWorker"
        )
        methods = {
            node.name: node for node in worker_class.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("run", "_progress_hook")
        }
        calls = {"completed": 0, "canceled": 0, "failed": 0}
        hook_entered = threading.Event()

        class FakeDownloader:
            def __init__(self, options):
                self.params = options

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                return {"id": "cancel-paused-transfer"}

            def process_ie_result(self, info, download=False):
                hook_entered.set()
                self.params["progress_hooks"][0]({
                    "status": "downloading",
                    "downloaded_bytes": 10,
                    "total_bytes": 100,
                })
                raise AssertionError("cancel should interrupt the paused hook")

        class SignalCounter:
            def __init__(self, key):
                self.key = key

            def emit(self, *args):
                calls[self.key] += 1

        class NoopSignal:
            def emit(self, *args):
                pass

        class WorkerStub:
            pass

        with tempfile.TemporaryDirectory() as folder:
            self_owner = WorkerStub()
            self_owner.url = "https://www.youtube.com/watch?v=cancel-paused-transfer"
            self_owner.folder = folder
            self_owner.media_type = "audio"
            self_owner.proxy_url = ""
            self_owner.cancel_event = threading.Event()
            self_owner.pause_event = threading.Event()
            self_owner._last_downloaded = 0
            self_owner._last_time = time.monotonic()
            self_owner._speed = 0.0
            self_owner.state = NoopSignal()
            self_owner.progress = NoopSignal()
            self_owner.completed = SignalCounter("completed")
            self_owner.canceled = SignalCounter("canceled")
            self_owner.failed = SignalCounter("failed")
            namespace = {
                "os": os,
                "time": time,
                "_resolve_youtube_output_path": lambda info, downloader: "",
                "_youtube_ffmpeg_executable": lambda: "",
                "normalize_proxy_url": lambda value: value,
                "__builtins__": __builtins__,
            }
            exec(
                compile(
                    ast.Module(
                        body=[methods["run"], methods["_progress_hook"]],
                        type_ignores=[],
                    ),
                    str(SOURCE_PATH),
                    "exec",
                ),
                namespace,
            )
            self_owner._progress_hook = types.MethodType(
                namespace["_progress_hook"], self_owner
            )
            previous = sys.modules.get("yt_dlp")
            sys.modules["yt_dlp"] = types.SimpleNamespace(YoutubeDL=FakeDownloader)
            worker_thread = threading.Thread(
                target=namespace["run"], args=(self_owner,)
            )
            try:
                worker_thread.start()
                self.assertTrue(
                    hook_entered.wait(2),
                    "download never reached its paused progress hook",
                )
                time.sleep(0.05)
                self.assertTrue(
                    worker_thread.is_alive(),
                    "paused transfer should wait until resume or cancellation",
                )
                self_owner.cancel_event.set()
                worker_thread.join(2)
                self.assertFalse(
                    worker_thread.is_alive(),
                    "cancellation did not release the paused progress hook",
                )
            finally:
                self_owner.pause_event.set()
                self_owner.cancel_event.set()
                if worker_thread.is_alive():
                    worker_thread.join(2)
                if previous is None:
                    sys.modules.pop("yt_dlp", None)
                else:
                    sys.modules["yt_dlp"] = previous

        self.assertEqual(calls["completed"], 0)
        self.assertEqual(calls["canceled"], 1)
        self.assertEqual(calls["failed"], 0)


if __name__ == "__main__":
    unittest.main()
