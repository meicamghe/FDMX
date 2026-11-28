# ADM Qt Quick / QML migration experiment

The production QWidget application remains the default. This branch does not
change its entry point, package configuration, or release artifacts.

## Preview and Windows test build

The standalone preview (`python -m qml_ui.main`) is intentionally disconnected. To run the experimental production QML interface with the real legacy download engine, use `python -m qml_ui.production_main`. The experimental Windows workflow builds a separate `ADM QML Preview` installer and portable package; the original Widgets package remains unchanged.

## Architecture
- `models.py`: typed Qt list model for normalized download snapshots; progress
  changes emit row-level `dataChanged` updates, while insert/remove/reorder
  events reset the model only when task identity/order changes.
- `adapter.py`: `FDMXDownloadAdapter`, a QObject facade over the legacy
  controller's task dictionary, history, workers and task-ID operations.
- `main.py`: standalone QGuiApplication preview, deliberately disconnected.
- `host.py`: optional embedding entry point for the existing production QApplication; returns the engine, adapter and QML root window.
- `Main.qml`: presentation only; no downloader logic.

Instantiate `FDMXDownloadAdapter(existing_fdmx_window)` on the controller's
GUI thread. It exposes sanitized task snapshots, bounded read-only history,
aggregate active/queued/completed/scheduled counts, total speed, and read-only
snapshots of the existing download settings. It provides task-ID
pause/resume/cancel/retry and queued-task schedule/clear/start-now slots. URLs,
tokens and credentials are not exposed.
Worker signals remain connected to the existing controller, and all controller
state access stays on its owning GUI thread.

**Important integration constraint:** the standalone preview uses
`QGuiApplication`, whereas the production controller is a QWidget and must
run under the existing `QApplication`. Do not create a second Qt application.
`host.create_qml_window(existing_controller)` now provides that optional host
path and is covered by a dedicated offscreen smoke test. The production startup
path still does not call it: Widgets remains the default and fallback until
real-download lifecycle, UI parity, packaging and Windows rendering are accepted.

The QML shell now includes a URL intake field that submits HTTP/HTTPS, YouTube
and magnet links through the existing controller pipeline. An optional future
ISO date/time can be supplied for HTTP/HTTPS and YouTube tasks; the timestamp is
preserved across metadata probing and the existing scheduler holds the task until
its due time. Magnet-link scheduling is intentionally rejected. QML-originated
HTTP tasks suppress the legacy detail popups so the QML list remains the primary
view; existing-file conflict and private GitHub authentication prompts still use
the legacy controller dialogs. The shell also has sidebar filtering (overview,
all, active, completed, scheduled, queued, failed and history), filename search
across downloads and history, visible rejection feedback, read-only settings,
queued-task schedule/clear/start-now actions, and pause/resume/cancel/retry
controls on eligible rows. Scheduler persistence failures are surfaced, and a
failed start-now operation restores and persists the previous schedule. History
is a read-only screen with timestamp, size and a safe failure notice; raw error
text, URLs and local paths are not exposed. Settings editing, bulk schedule
management, history deletion/export, torrent-specific controls and analytics
drill-down remain unfinished. The bridge is covered by mocked intake and scheduler tests plus a real local-HTTP integration test. That test opens the production QML host with the existing QWidget controller, submits a URL through the QML bridge, exercises the real metadata probe, queue and legacy DownloadWorker, verifies the exact downloaded bytes, and confirms that no legacy detail dialog is opened. This is a controlled local-network test, not acceptance of public-internet transfers. Live external HTTP sources, GitHub authentication, YouTube, torrent transfers, and real-world proxy configurations still require separate validation.

## Remaining acceptance gates
1. Run controlled real-download lifecycle and queue-scheduling comparisons against the Widgets UI.
2. Add editable typed settings, scheduler operations, history management/export and analytics drill-down.
3. Validate Windows DPI scaling, GPU/software rendering, packaging, startup and memory/CPU use.
4. Verify that QML host failure cleanly leaves the Widgets UI usable.
5. Require feature parity and explicit approval before considering cutover.
