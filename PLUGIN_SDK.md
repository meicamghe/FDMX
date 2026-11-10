# FDMX Plugin SDK 1.7

## Install
Create a folder per plugin under `%USERPROFILE%\\.fdmx\\plugins\\<plugin-id>\\` on Windows or `~/.fdmx/plugins/<plugin-id>/` on Linux. Place `plugin.json` and the Python entrypoint in that folder.

Keep `fdmx_plugin_sdk.py` and `fdmx_plugin_host.py` beside the FDMX main script. The example is in `plugins/example_hello_world/`.

## Manifest
Required: `id`, `name`, `version`, `entrypoint`, `permissions`. Entrypoint must be a Python file directly inside the plugin folder. Supported permissions: `app.events`, `app.log`, `ui.notifications`.

## Plugin lifecycle

Open the Plugin Manager and use **Install Folder** to install a trusted plugin
directory containing a valid `plugin.json` and its entrypoint. Installation
validates the manifest and supported permissions, rejects symbolic links, stages
the copy, and moves it into place only after validation. Newly installed plugins
remain disabled until explicitly enabled.

Use **Enable**, **Load**, and **Disable** to control execution. **Uninstall**
removes plugin code but preserves per-plugin settings and data by default.
Applications integrating the SDK can store JSON-compatible preferences with
`manager.set_plugin_settings(plugin_id, settings)` and read them with
`manager.get_plugin_settings(plugin_id)`. The default data directory is
`<plugin-root-parent>/plugin_data/<plugin-id>/`.

For an explicit full removal, call
`manager.uninstall(plugin_id, remove_data=True)`; this also removes the
plugin's saved settings and data directory. This operation is intentionally
separate from the normal UI uninstall action to reduce accidental data loss.
State writes use a temporary file and atomic replacement. If uninstall state
persistence fails, the plugin directory is restored.

Only install plugins from sources you trust. Process separation is not a
security sandbox and does not make untrusted Python code safe.

## Plugin signing and publisher trust

SDK 1.4 supports detached Ed25519 signatures in `plugin.sig`. The signature
covers a deterministic manifest of SHA-256 hashes for every regular package
file except `plugin.sig` itself. Symbolic links and special files are rejected.
Changing the manifest, entrypoint, or any other packaged file invalidates the
signature.

Install the optional signing dependency with `python -m pip install cryptography`.
The publisher generates an Ed25519 key pair and keeps the private key offline:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

key = Ed25519PrivateKey.generate()
private_pem = key.private_bytes(serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
public_pem = key.public_key().public_bytes(serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo)
open("publisher-private.pem", "wb").write(private_pem)  # keep private; never distribute
open("publisher-public.pem", "wb").write(public_pem)
```

Sign a completed plugin folder before distributing it:

```python
from pathlib import Path
from fdmx_plugin_sdk import sign_plugin_folder
fingerprint = sign_plugin_folder(Path("my_plugin"), Path("publisher-private.pem").read_bytes())
print(fingerprint)
```

The plugin folder now contains `plugin.sig`. Distribute the public key or its
fingerprint through a separate trusted channel. In FDMX Plugin Manager, inspect
the fingerprint and choose **Trust Publisher** only after independently
verifying it. Trust is stored locally in `trusted_publishers.json`.

Status meanings: `trusted` = valid signature from a locally trusted key;
`unknown_publisher` = valid signature but key not trusted yet; `unsigned` =
no signature; `invalid` = signature or package hash mismatch; `unavailable` =
cryptography is not installed. Invalid signatures are always blocked. Unsigned
and unknown packages require explicit confirmation to install and load. A
signature verifies package integrity and publisher-key possession; it does
not prove that the plugin is benign or safe.



## In-app plugin repository browser

Plugin Manager includes a **Plugin Repository** action. Enter an HTTPS catalog
URL, choose an available package, then install it or update an existing plugin.
New packages remain disabled after installation. Existing plugins update only
when the archive digest matches, the Ed25519 signature is valid and trusted,
the publisher key matches the installed publisher, and the version increases.
The UI asks for explicit confirmation before installing a package whose
publisher is not yet trusted. Never trust a publisher fingerprint solely
because it appears in the catalog; verify it independently.

## HTTPS plugin repository and secure updates

The optional repository client is in `fdmx_plugin_repository.py`. A catalog is
UTF-8 JSON using this structure:

```json
{
  "format": "FDMX-PLUGIN-REPOSITORY-V1",
  "plugins": [
    {
      "id": "example_hello_world",
      "version": "1.2.0",
      "archive_url": "https://downloads.example/plugins/example_hello_world-1.2.0.zip",
      "sha256": "64-character-lowercase-hex-archive-digest"
    }
  ]
}
```

Each ZIP must contain `plugin.json`, the entrypoint, and `plugin.sig` directly
at its root. The catalog digest detects transport/corruption errors; the
Ed25519 package signature remains the publisher-authentication mechanism.
Catalogs and archives must use HTTPS. Downloads and expanded archives have
size/file-count limits, and path traversal, symbolic links, and malformed ZIPs
are rejected.

Example:

```python
from fdmx_plugin_repository import PluginRepository

repository = PluginRepository("https://downloads.example/fdmx/plugins.json")
available = repository.list_plugins()
updated = repository.update(plugin_manager, "example_hello_world")
print(updated.version, updated.signature_status)
```

Updates require a valid signature from an already trusted publisher, the same
publisher key as the installed plugin, a matching catalog/manifest identity,
and a strictly newer numeric version. The new package is staged and verified
again before replacement. The previous signed package is retained under
`<plugin-root>/.history/<plugin-id>/` after a successful update. Plugin Manager
can list verified historical versions and restore one with **Rollback**. Each
rollback re-verifies the Ed25519 signature, trusted publisher fingerprint,
plugin identity, entrypoint, and permissions before atomically replacing the
current version. The displaced current version is retained in history too. Plugin settings and
data are preserved; the updated plugin is not automatically started. Publisher
key rotation is deliberately not automatic and requires a separate trust
workflow.

The repository client is an SDK/API foundation in this release; a hosted public
catalog service and in-app repository browser are not included yet. Only add
catalog URLs from sources you trust. HTTPS and SHA-256 alone do not establish
publisher trust.

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
