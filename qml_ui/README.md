# ADM Qt Quick / QML migration experiment

The production QWidget application remains the default. This branch does not
change its entry point, package configuration, or release artifacts.

## Preview
```bash
python -m pip install PySide6
python -m qml_ui.main
```

## Architecture
- `models.py`: typed Qt list model for normalized download snapshots.
- `adapter.py`: `FDMXDownloadAdapter`, a QObject facade over the legacy
  controller's task dictionary, history, workers and task-ID operations.
- `main.py`: standalone QGuiApplication preview, deliberately disconnected.
- `host.py`: optional embedding entry point for the existing production QApplication; returns the engine, adapter and QML root window.
- `Main.qml`: presentation only; no downloader logic.

Instantiate `FDMXDownloadAdapter(existing_fdmx_window)` on the controller's
GUI thread. It exposes sanitized task snapshots, bounded read-only history,
aggregate active/queued/completed/scheduled counts, total speed, and read-only
snapshots of the existing download settings. It provides task-ID
pause/resume/cancel/retry slots. URLs, tokens and credentials are not exposed.
Worker signals remain connected to the existing controller, and all controller
state access stays on its owning GUI thread.

**Important integration constraint:** the standalone preview uses
`QGuiApplication`, whereas the production controller is a QWidget and must
run under the existing `QApplication`. Do not create a second Qt application.
The next host integration step must load QML from the existing QApplication
and inject the adapter while preserving the Widgets UI as the fallback.

The QML download rows expose pause, resume, cancel and retry controls. History
is currently read-only, while scheduled timestamps and category are included in
task snapshots. Scheduler edits, settings changes, history management/export,
torrent-specific operations and analytics drill-down need additional explicit
typed slots before those screens can claim parity.

## Remaining acceptance gates
1. Embed QML inside the existing QApplication without replacing the default UI.
2. Test task lifecycle and queue scheduling against the Widgets UI.
3. Add typed settings, scheduler, history and analytics interfaces.
4. Validate Windows DPI scaling, GPU/software rendering, packaging and resource use.
5. Require feature parity and explicit approval before considering cutover.
