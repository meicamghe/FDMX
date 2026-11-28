# ADM Qt Quick / QML Preview

This directory contains an isolated Qt Quick shell experiment. It does **not**
replace the production PySide6 Widgets interface and does not start or manage
downloads yet.

## Run

From the repository root, with the project's PySide6 environment active:

```bash
python -m pip install PySide6
python -m qml_ui.main
```

## Architecture boundary

- `main.py` owns the QGuiApplication and QQmlApplicationEngine.
- `AppBridge` is the narrow QObject exposed to QML.
- `models.py` defines the typed, read-only `DownloadListModel` contract.
- `Main.qml` contains presentation only and consumes that model.
- The model accepts normalized snapshots through `replace_downloads()`.
- The production download engine remains in `FDMX_v6_50.py` and is not imported.

The model is intentionally empty in this preview. It proves the QML-facing data
contract, not live download telemetry or download controls.

## Migration sequence

1. Validate QML startup, window sizing, fonts, DPI scaling and GPU/software
   rendering on supported Windows machines.
2. Extract download, queue, scheduler and settings services from the monolithic
   production module behind Python interfaces.
3. Add a tested adapter that converts existing task state into normalized
   snapshots for `DownloadListModel`.
4. Expose pause, resume, cancel and retry through explicit bridge slots, with
   ownership and thread-affinity rules documented and tested.
5. Replace preview placeholders with real models, one screen at a time.
6. Compare behavior against the Widgets application before considering cutover.

Do not remove the production Widgets UI or change release packaging until the
QML implementation passes functional parity and packaging tests.
