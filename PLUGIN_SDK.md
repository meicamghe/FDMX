# FDMX Plugin SDK 1.1

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
