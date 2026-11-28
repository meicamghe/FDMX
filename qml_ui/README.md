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
`host.create_qml_window(existing_controller)` now provides that optional host
path and is covered by a dedicated offscreen smoke test. The production startup
path still does not call it: Widgets remains the default and fallback until
real-download lifecycle, UI parity, packaging and Windows rendering are accepted.

The QML shell now has working sidebar filtering (overview, all, active,
completed and scheduled), filename search, a read-only settings snapshot dialog,
and pause/resume/cancel/retry controls on eligible task rows. Scheduled timestamps
and categories are included in task snapshots. History remains a read-only adapter
property and is not yet a dedicated history screen. Scheduler edits, settings changes, history management/export,
torrent-specific operations and analytics drill-down need additional explicit
typed slots before those screens can claim parity.

## Remaining acceptance gates
1. Run controlled real-download lifecycle and queue-scheduling comparisons against the Widgets UI.
2. Add editable typed settings, scheduler operations, history management/export and analytics drill-down.
3. Validate Windows DPI scaling, GPU/software rendering, packaging, startup and memory/CPU use.
4. Verify that QML host failure cleanly leaves the Widgets UI usable.
5. Require feature parity and explicit approval before considering cutover.
