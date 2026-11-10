# FDMX Plugin SDK 1.2

## Install
Create a folder per plugin under `%USERPROFILE%\\.fdmx\\plugins\\<plugin-id>\\` on Windows or `~/.fdmx/plugins/<plugin-id>/` on Linux. Place `plugin.json` and the Python entrypoint in that folder.

Keep `fdmx_plugin_sdk.py` and `fdmx_plugin_host.py` beside the FDMX main script. The example is in `plugins/example_hello_world/`.

## Manifest
Required: `id`, `name`, `version`, `entrypoint`, `permissions`. Entrypoint must be a Python file directly inside the plugin folder. Supported permissions: `app.events`, `app.log`, `ui.notifications`.

## Plugin contract
Define `register(api)`; optional `shutdown()` runs when the worker is stopped. API: `api.log(message)`, `api.notify(title, message)`, `api.on(event_name, callback)`. Events: `app.started`, `download.completed`, `download.failed`.

Plugins run in separate Python processes. IPC uses JSON Lines with a 1 MiB message limit; startup timeout is 8 seconds.

## Security model
Separate processes improve crash containment and keep plugin callbacks outside the GUI process. This is **not an OS security sandbox**. A plugin still runs as the current user and can access files, network resources, and subprocesses permitted to that account. SDK permissions restrict only FDMX RPC methods, not arbitrary Python code. Install only trusted plugins. Strong isolation requires OS-level controls (for example Windows AppContainer or Linux namespaces/seccomp), which are not implemented here.


## Automated tests
The repository includes cross-platform worker tests in `tests/test_plugin_sdk.py`. GitHub Actions runs them on Windows and Ubuntu with Python 3.11 and 3.12. Run locally with:

```bash
python -m pip install PySide6
python -m py_compile fdmx_plugin_sdk.py fdmx_plugin_host.py tests/test_plugin_sdk.py
python -m unittest discover -s tests -v
```

## Packaged / PyInstaller builds

The plugin worker must be shipped as a separate **console** executable so its
JSON-lines standard-output channel remains available. Build it from the
repository root before packaging FDMX:

**Windows (PowerShell):**

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --console --name fdmx_plugin_worker fdmx_plugin_host.py
```

Copy `dist\fdmx_plugin_worker.exe` beside `FDMX.exe` in the final distribution.
The SDK automatically launches this companion executable when FDMX is frozen
by PyInstaller. It also checks PyInstaller's temporary bundle directory.

**Linux:**

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --console --name fdmx_plugin_worker fdmx_plugin_host.py
```

Copy `dist/fdmx_plugin_worker` beside the FDMX executable and preserve its
executable permission. In source/development runs, the SDK continues to launch
the worker with the active Python interpreter.

The CI workflow `.github/workflows/plugin-worker-build.yml` builds and smoke-tests
the standalone worker on Windows and Ubuntu with Python 3.11 and 3.12.
