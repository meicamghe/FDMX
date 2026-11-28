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


def test_download_details_are_less_redundant_without_removing_progress_bar():
    start = SOURCE.index("class DownloadDetailsDialog")
    end = SOURCE.index("class ", start + 10)
    dialog = SOURCE[start:end]
    assert "self.progress_bar = QProgressBar()" in dialog
    assert 'self.progress_bar.setFormat(f"{percent}%  —  {size_text}")' in dialog
    assert "Downloaded: {size_text}" not in dialog
    assert "Type: {content_type}" not in dialog
    assert "Fixed connection mode:" not in dialog


def test_windows_theme_presets_and_saved_selection_are_available():
    for theme in ('addItem("Light", "light")', 'addItem("Dark", "dark")', 'addItem("Midnight", "midnight")', 'addItem("Violet", "violet")'):
        assert theme in SOURCE
    assert 'self.settings.value("theme", default_theme, type=str)' in SOURCE


def test_schedule_clear_all_preserves_download_tasks():
    assert 'clear_all_schedules.clicked.connect(self.clear_all_schedules)' in SOURCE
    start = SOURCE.index("    def clear_all_schedules(self):")
    end = SOURCE.index("    def start_selected_now(self):", start)
    method = SOURCE[start:end]
    assert 'task["scheduled_at"] = ""' in method
    assert "self.tasks.pop" not in method
    assert "QMessageBox.Yes | QMessageBox.No" in method


def test_browser_download_confirmation_precedes_queue_start():
    start = SOURCE.index("    def on_file_info_ready(")
    end = SOURCE.index("    def add_torrent_file(", start)
    method = SOURCE[start:end]
    assert "Confirm browser download" in method
    assert "File size:" in method and "File type:" in method and "Source:" in method
    assert 'addButton("Start Download"' in method
    assert method.index("confirm.exec()") < method.index('task["status"] = "Queued"')
