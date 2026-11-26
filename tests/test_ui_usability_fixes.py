"""Regression checks for startup and desktop usability improvements."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "FDMX_v6_50.py").read_text(encoding="utf-8")


def test_startup_timer_includes_heavy_gui_imports():
    assert SOURCE.index("_MODULE_STARTED_AT = time.perf_counter()") < SOURCE.index("from PySide6.QtCore")
    assert "QTimer.singleShot(0, self.finish_deferred_startup)" in SOURCE
    assert "def finish_deferred_startup(self):" in SOURCE


def test_open_containing_folder_reveals_the_file():
    start = SOURCE.index("    def open_folder(self):")
    end = SOURCE.index("    def timerEvent(self, event):", start)
    method = SOURCE[start:end]
    assert '["explorer.exe", "/select,"' in method
    assert '["open", "-R", target]' in method
    assert "org.freedesktop.FileManager1.ShowItems" in method
    assert '["xdg-open", os.path.dirname(target)]' in method


def test_update_prompt_keeps_release_notes_collapsed_and_compact():
    start = SOURCE.index("    def on_update_available(")
    end = SOURCE.index("    def start_update_download(", start)
    method = SOURCE[start:end]
    assert "setInformativeText" in method
    assert "setDetailedText" in method
    assert "len(highlights) >= 3" in method
    assert "short_notes[:357]" in method
    assert "notes[:12000]" not in method
