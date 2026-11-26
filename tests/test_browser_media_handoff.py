"""Regression tests for automatic browser-to-desktop handoff and media choices."""
import ast
import json
from pathlib import Path
import unittest
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")
CHROME = ROOT / "browser-extensions/chrome"
FIREFOX = ROOT / "browser-extensions/firefox"


def load_protocol_parser():
    tree = ast.parse(SOURCE)
    wanted = {"_safe_int", "is_youtube_url", "parse_gns_protocol_request"}
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace = {"urllib": urllib, "re": __import__("re")}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "FDMX_v6_50.py", "exec"), namespace)
    return namespace["parse_gns_protocol_request"]


class BrowserMediaHandoffTests(unittest.TestCase):
    def test_application_source_compiles_and_version_is_bumped(self):
        compile(SOURCE, "FDMX_v6_50.py", "exec")
        self.assertIn('APP_VERSION = "6.53"', SOURCE)

    def test_protocol_parser_accepts_valid_direct_download(self):
        parse = load_protocol_parser()
        result = parse("gnsdownloader://download?url=" + urllib.parse.quote("https://example.com/file.zip", safe=""))
        self.assertEqual(result, {
            "action": "download",
            "url": "https://example.com/file.zip",
            "resolved_url": "",
        })

    def test_protocol_parser_accepts_valid_youtube_audio_and_quality(self):
        parse = load_protocol_parser()
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        target = "gnsdownloader://youtube?" + urllib.parse.urlencode({
            "url": url, "media_type": "video", "height": "1080"
        })
        result = parse(target)
        self.assertEqual(result["action"], "youtube")
        self.assertEqual(result["media_type"], "video")
        self.assertEqual(result["height"], 1080)
        audio = parse("gnsdownloader://youtube?" + urllib.parse.urlencode({"url": url, "media_type": "audio", "audio_bitrate": "160"}))
        self.assertEqual(audio["media_type"], "audio")
        self.assertEqual(audio["audio_bitrate"], 160)
        website = parse("gnsdownloader://website?" + urllib.parse.urlencode({"url": "https://example.com/music"}))
        self.assertEqual(website, {"action": "website", "url": "https://example.com/music"})

    def test_protocol_parser_rejects_invalid_scheme_and_signed_url_host(self):
        parse = load_protocol_parser()
        self.assertIsNone(parse("gnsdownloader://download?url=file%3A%2F%2F%2Fetc%2Fpasswd"))
        bad = "gnsdownloader://download?" + urllib.parse.urlencode({
            "url": "https://github.com/owner/repo/actions/runs/1/artifacts/2",
            "resolved_url": "https://github.com/owner/repo/private.zip"
        })
        self.assertIsNone(parse(bad))

    def test_browser_bridge_has_youtube_format_and_queue_routes(self):
        self.assertIn('route == "/youtube/formats"', SOURCE)
        self.assertIn('route == "/youtube/download"', SOURCE)
        self.assertIn('route == "/website/open"', SOURCE)
        self.assertIn("window.browser_website_requested.emit(url)", SOURCE)
        self.assertIn("window.browser_youtube_requested.emit(url, media_type, height, audio_bitrate)", SOURCE)
        self.assertIn('"qualities": qualities', SOURCE)
        self.assertIn('"audio_available": audio_available', SOURCE)
        self.assertIn('"audio_qualities":', SOURCE)

    def test_youtube_quality_is_applied_to_worker_and_survives_restart(self):
        self.assertIn('bestvideo[height<={self.max_height}]+bestaudio/best[height<={self.max_height}]', SOURCE)
        self.assertIn('"max_height": max_height', SOURCE)
        self.assertIn('"max_abr": max_abr', SOURCE)
        self.assertIn("self.max_abr", SOURCE)
        self.assertIn('"max_height", "max_abr", "scheduled_at"', SOURCE)
        self.assertIn('max_height=0', SOURCE)
        self.assertIn('task.get("max_height", 0)', SOURCE)

    def test_tools_menu_exposes_browser_install_guide(self):
        self.assertIn('tools_menu.addAction("Install browser extensions…", self.show_browser_extension_help)', SOURCE)
        self.assertIn("addons.mozilla.org/en-US/firefox/addon/gns-download-manager/", SOURCE)
        self.assertIn("chrome://extensions", SOURCE)
        self.assertIn("Load unpacked", SOURCE)

    def test_desktop_protocol_is_registered_on_windows_and_linux(self):
        iss = (ROOT / "installer/FDMX.iss").read_text(encoding="utf-8")
        linux = (ROOT / ".github/workflows/build-fdmx-linux.yml").read_text(encoding="utf-8")
        self.assertIn('Subkey: "gnsdownloader"', iss)
        self.assertIn("HKEY_CURRENT_USER", SOURCE)
        self.assertIn("register_gns_protocol_handler()", SOURCE)
        self.assertIn('""%1"""', iss)
        self.assertIn("x-scheme-handler/gnsdownloader", linux)
        self.assertIn("Exec=gns-downloader %u", linux)

    def test_both_browser_manifests_have_matching_brand_and_version(self):
        chrome = json.loads((CHROME / "manifest.json").read_text(encoding="utf-8"))
        firefox = json.loads((FIREFOX / "manifest.json").read_text(encoding="utf-8"))
        for manifest in (chrome, firefox):
            self.assertEqual(manifest["name"], "GNS Downloader")
            self.assertEqual(manifest["version"], "1.3.0")
            self.assertIn("downloads", manifest["permissions"])
            self.assertIn("media-detect.js", str(manifest["content_scripts"]))
        self.assertEqual(
            firefox["applications"]["gecko"]["id"],
            "fdmx-browser@gns.local",
        )

    def test_context_menu_and_automatic_download_handoff_exist_in_both_browsers(self):
        for browser in (CHROME, FIREFOX):
            source = (browser / "background.js").read_text(encoding="utf-8")
            self.assertIn("Download with GDM", source)
            self.assertIn("chrome.downloads.onCreated.addListener", source)
            self.assertIn("gnsdownloader://", source)
            self.assertIn("chrome.downloads.cancel(item.id)", source)

    def test_youtube_and_direct_media_overlay_offers_user_choice(self):
        for browser in (CHROME, FIREFOX):
            source = (browser / "media-detect.js").read_text(encoding="utf-8")
            self.assertIn("GNS_YOUTUBE_FORMATS", source)
            self.assertIn("Audio only", source)
            self.assertIn("Download with GNS", source)
            self.assertIn("GNS_SEND_URL", source)
            self.assertIn("GNS_OPEN_WEBSITE", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
