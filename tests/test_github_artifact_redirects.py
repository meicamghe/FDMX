"""Regression tests for redirect-based download metadata probing."""
import ast
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")


class _Headers(dict):
    def get_content_charset(self):
        return "utf-8"


class _Response:
    def __init__(self, url):
        self.headers = _Headers({
            "Content-Length": "4096",
            "Content-Type": "application/zip",
            "Content-Disposition": 'attachment; filename="ApnaWin-artifact.zip"',
            "Accept-Ranges": "bytes",
        })
        self.status = 200
        self.url = url
        self.read_sizes = []
        self.closed = False

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_sizes.append(size)
        return b"Z"[:size]

    def close(self):
        self.closed = True


def _load_file_info_run():
    tree = ast.parse(SOURCE)
    worker = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FileInfoWorker"
    )
    method = next(
        node for node in worker.body
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    namespace = {
        "urllib": urllib,
        "threading": threading,
        "Message": __import__("email.message", fromlist=["Message"]).Message,
        "os": __import__("os"),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), "<FileInfoWorker.run>", "exec"), namespace)
    return namespace["run"]


class GitHubArtifactRedirectRegressionTests(unittest.TestCase):
    def test_metadata_uses_get_first_and_accepts_resolved_two_hop_url(self):
        run = _load_file_info_run()
        final_url = "https://actions-artifacts.example.invalid/signed/ApnaWin-artifact.zip"
        response = _Response(final_url)
        requests = []

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            if len(requests) == 1:
                # The mocked transport represents GitHub following its two
                # redirects and returning the final object-storage response.
                return response
            raise AssertionError("GET should succeed without a HEAD fallback")

        emitted = []
        worker = SimpleNamespace(
            url="https://github.com/meicamghe/ApnaWin/actions/runs/44041949454/artifacts/14309364039?utm_source=chatgpt.com",
            cancel_event=threading.Event(),
            _response_lock=threading.Lock(),
            _active_response=None,
            info_ready=SimpleNamespace(emit=emitted.append),
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            run(worker)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0].get_method(), "GET")
        self.assertIn("Chrome/", requests[0][0].get_header("User-agent"))
        self.assertEqual(emitted[0]["final_url"], final_url)
        self.assertEqual(emitted[0]["size"], 4096)
        self.assertEqual(emitted[0]["name"], "ApnaWin-artifact.zip")
        self.assertEqual(response.read_sizes, [1])
        self.assertTrue(response.closed)

    def test_falls_back_to_head_if_get_is_rejected(self):
        run = _load_file_info_run()
        response = _Response("https://cdn.example.invalid/file.zip")
        methods = []

        def fake_urlopen(request, timeout):
            methods.append(request.get_method())
            if request.get_method() == "GET":
                raise urllib.error.HTTPError(request.full_url, 405, "Method Not Allowed", {}, None)
            return response

        emitted = []
        worker = SimpleNamespace(
            url="https://example.invalid/file.zip",
            cancel_event=threading.Event(),
            _response_lock=threading.Lock(),
            _active_response=None,
            info_ready=SimpleNamespace(emit=emitted.append),
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            run(worker)

        self.assertEqual(methods, ["GET", "HEAD"])
        self.assertEqual(emitted[0]["size"], 4096)
        self.assertEqual(emitted[0]["final_url"], response.url)


if __name__ == "__main__":
    unittest.main()
