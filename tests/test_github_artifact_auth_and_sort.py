"""Offline regressions for authenticated GitHub Actions artifacts and list ordering."""
from pathlib import Path
import ast
import datetime
import urllib.parse
import urllib.request
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")


def load_helpers(*names):
    tree = ast.parse(SOURCE)
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
    namespace = {"urllib": urllib, "datetime": datetime}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<gns-helpers>", "exec"), namespace)
    return namespace


class GitHubArtifactAndOrderingTests(unittest.TestCase):
    def test_current_application_source_compiles(self):
        compile(SOURCE, "FDMX_v6_50.py", "exec")

    def test_browser_artifact_link_becomes_authenticated_zip_api(self):
        helpers = load_helpers("github_actions_artifact_api_url")
        resolve = helpers["github_actions_artifact_api_url"]
        self.assertEqual(
            resolve("https://github.com/meicamghe/ApnaWin/actions/runs/44041949454/artifacts/14309364039?utm_source=chatgpt.com"),
            "https://api.github.com/repos/meicamghe/ApnaWin/actions/artifacts/14309364039/zip",
        )

    def test_short_artifact_page_link_is_supported(self):
        resolve = load_helpers("github_actions_artifact_api_url")["github_actions_artifact_api_url"]
        self.assertEqual(
            resolve("https://github.com/acme/project/actions/artifacts/123456"),
            "https://api.github.com/repos/acme/project/actions/artifacts/123456/zip",
        )

    def test_existing_api_zip_url_is_preserved(self):
        resolve = load_helpers("github_actions_artifact_api_url")["github_actions_artifact_api_url"]
        url = "https://api.github.com/repos/acme/project/actions/artifacts/123456/zip"
        self.assertEqual(resolve(url), url)

    def test_unrelated_github_page_is_not_rewritten(self):
        resolve = load_helpers("github_actions_artifact_api_url")["github_actions_artifact_api_url"]
        url = "https://github.com/acme/project/releases"
        self.assertEqual(resolve(url), "")

    def test_newest_completed_download_is_first_and_other_order_is_stable(self):
        helpers = load_helpers("_task_completion_timestamp", "_sort_completed_tasks")
        items = [
            ("active-1", {"status": "Downloading"}),
            ("old", {"status": "Completed", "completed_at": 100}),
            ("queued", {"status": "Queued"}),
            ("new", {"status": "Completed", "completed_at": 300}),
            ("middle", {"status": "Completed", "completed_at": 200}),
            ("active-2", {"status": "Paused"}),
        ]
        result = helpers["_sort_completed_tasks"](items)
        self.assertEqual(
            [task_id for task_id, _ in result],
            ["new", "middle", "old", "active-1", "queued", "active-2"],
        )

    def test_legacy_history_time_is_used_when_timestamp_is_missing(self):
        helpers = load_helpers("_history_entry_timestamp")
        timestamp = helpers["_history_entry_timestamp"]({"time": "2026-11-17 11:30:00"})
        self.assertGreater(timestamp, 0)

    def test_cross_origin_redirect_does_not_forward_github_token(self):
        handler = load_helpers("_CredentialSafeRedirectHandler")["_CredentialSafeRedirectHandler"]()
        request = urllib.request.Request(
            "https://api.github.com/repos/acme/project/actions/artifacts/123/zip",
            headers={"Authorization": "Bearer secret-token", "Accept": "application/vnd.github+json"},
        )
        redirected = handler.redirect_request(
            request, None, 302, "Found", {},
            "https://objects.githubusercontent.com/github-production-release-asset/123",
        )
        self.assertIsNotNone(redirected)
        self.assertNotIn("Authorization", redirected.headers)
        self.assertNotIn("Authorization", redirected.unredirected_hdrs)
        self.assertEqual(redirected.get_header("Accept"), "application/vnd.github+json")

    def test_same_origin_redirect_keeps_github_token(self):
        handler = load_helpers("_CredentialSafeRedirectHandler")["_CredentialSafeRedirectHandler"]()
        request = urllib.request.Request(
            "https://api.github.com/repos/acme/project/actions/artifacts/123/zip",
            headers={"Authorization": "Bearer secret-token"},
        )
        redirected = handler.redirect_request(
            request, None, 302, "Found", {},
            "https://api.github.com/repos/acme/project/actions/artifacts/123/zip?download=1",
        )
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret-token")

    def test_artifact_auth_is_applied_only_to_github_api_requests(self):
        self.assertIn('headers["Authorization"] = f"Bearer {self.github_token}"', SOURCE)
        self.assertIn('headers["X-GitHub-Api-Version"] = "2022-11-28"', SOURCE)
        self.assertIn('github_actions_artifact_api_url(url) or url', SOURCE)
        self.assertIn('find_github_cli_token()', SOURCE)
        self.assertIn('QLineEdit.Password', SOURCE)
        self.assertIn('"github_token": github_token', SOURCE)
        self.assertNotIn('"github_token", "post_action_enabled"', SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
