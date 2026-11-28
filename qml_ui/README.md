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

On Windows, run the same command from the activated virtual environment.

## Architecture boundary

- `main.py` owns the QGuiApplication and QQmlApplicationEngine.
- `AppBridge` is the narrow QObject exposed to QML.
- `Main.qml` contains presentation only.
- The production download engine remains in `FDMX_v6_50.py` and is not imported
  by this preview.

The status values shown as em dashes are intentionally placeholders, not
download-engine telemetry.

## Migration sequence

1. Validate QML startup, window sizing, fonts, DPI scaling and GPU/software
   rendering on supported Windows machines.
2. Extract download, queue, scheduler and settings services from the monolithic
   production module behind Python interfaces.
3. Expose those services through typed QObject models and signals/slots.
4. Replace preview placeholders with real models, one screen at a time.
5. Compare behavior against the Widgets application before considering cutover.

Do not remove the production Widgets UI or change release packaging until the
QML implementation passes functional parity and packaging tests.
