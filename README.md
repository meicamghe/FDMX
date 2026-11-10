# FDMX — Download Manager

FDMX is a desktop download manager built with **Python** and **PySide6 (Qt for Python)**. It provides multi-connection HTTP/HTTPS downloads, task controls, download history, browser hand-off, and an extensible plugin system.

**زبان فارسی:** [راهنمای فارسی نصب، اجرا و ساخت فایل EXE](docs/README_FA.md)

> **Development status:** This repository contains multiple historical versions. The current development-branch desktop entry point is `FDMX_v6_36.py` (application version 6.36). The Ubuntu-themed variant is `ubuntu.py`. Plugin SDK 1.7 work is present on the development branch, but its latest integration-test CI run failed; treat that SDK revision as under development, not as a stable production release. No installer or signed end-user release is currently published.

## Project overview

FDMX has evolved from a basic downloader into a desktop application with download management, browser integration, and a plugin platform. The repository preserves earlier numbered scripts for development history; use the current entry point rather than launching an old numbered file.

### Main capabilities

- HTTP and HTTPS downloads with configurable multi-connection transfers.
- Pause, resume, cancel, and retry controls for downloads.
- Download queue/task persistence and download history.
- Download scheduling and transfer speed controls.
- Destination selection and automatic file-type categorization.
- Browser integration through local loopback communication.
- Chrome and Firefox extension source code.
- Plugin Manager with plugin install, enable/disable, load/unload, and uninstall workflows.
- Plugin SDK with manifest and permission validation, worker-process execution, and plugin settings/data storage.
- Ed25519 plugin signatures, publisher trust, and HTTPS plugin repository/update support.
- Plugin update history and signed-version rollback support in the current SDK development work.

Some features depend on the remote server, browser, plugin dependencies, or the selected application build. Browser media extraction and torrent-related workflows should be considered experimental unless separately validated.

## Current repository structure

| Path | Purpose |
|---|---|
| `FDMX_v6_36.py` | Current development-branch Windows/desktop application entry point (v6.36) |
| `ubuntu.py` | Ubuntu-themed desktop variant; separate build with its own compatibility testing |
| `fdmx_plugin_sdk.py` | Plugin manager, validation, signing/trust, update history and rollback |
| `fdmx_plugin_host.py` | Separate plugin worker process |
| `fdmx_plugin_repository.py` | HTTPS plugin catalog and package/update client |
| `plugins/example_hello_world/` | Example plugin |
| `tests/` | Plugin SDK, repository and worker tests |
| `browser-extensions/chrome/` | Chrome extension |
| `browser-extensions/firefox/` | Firefox extension |
| `PLUGIN_SDK.md` | Plugin SDK technical documentation |
| `docs/README_FA.md` | Persian user guide |

## Requirements

- Windows 10/11 is the primary desktop target.
- Python 3.11 or 3.12 is recommended for development and SDK test parity.
- PySide6 for the graphical interface.
- `cryptography` for Ed25519 plugin signature verification/signing features.
- PyInstaller only when creating standalone executables.
- Inno Setup only when creating a traditional Windows setup installer.

## Run from source on Windows

Open PowerShell in the repository directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6 cryptography
python FDMX_v6_36.py
```

If PowerShell blocks virtual-environment activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install PySide6 cryptography
python FDMX_v6_36.py
```

To try the Ubuntu-themed variant:

```powershell
python ubuntu.py
```

The Ubuntu-themed variant has a separate code path and should be tested on the target Linux distribution before being treated as a supported Linux release.

## Run from source on Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
git clone https://github.com/meicamghe/FDMX.git
cd FDMX
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6 cryptography
python ubuntu.py
```

Linux package/runtime requirements can vary by distribution and desktop environment. This source-run procedure is not a claim that a Linux installer or AppImage is currently published.

## Create a standalone Windows EXE

A standalone executable can be built locally with PyInstaller. Build on Windows for Windows; PyInstaller is not a cross-compiler.

### 1. Prepare the build environment

```powershell
py -3.12 -m venv .build-venv
.\.build-venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6 cryptography pyinstaller
```

### 2. Build the plugin worker

The plugin SDK launches its worker as a separate process. Package it as a **console** executable so its JSON-lines standard-output protocol remains intact:

```powershell
pyinstaller --noconfirm --clean --onefile --console --name fdmx_plugin_worker fdmx_plugin_host.py
```

### 3. Build the graphical application

```powershell
pyinstaller --noconfirm --clean --onefile --windowed --name FDMX --collect-all PySide6 --collect-all cryptography FDMX_v6_36.py
```

### 4. Put the worker beside the application

```powershell
Copy-Item .\dist\fdmx_plugin_worker.exe .\dist\ -Force
```

The worker build already creates `dist\\fdmx_plugin_worker.exe`. Building the main application afterward creates `dist\\FDMX.exe`; both files should remain in the same `dist` folder. Do not copy a file onto itself. The distribution should contain at least:

```text
dist/
  FDMX.exe
  fdmx_plugin_worker.exe
```

Run `dist\FDMX.exe`. Test the EXE on a clean Windows 10/11 machine that does not have Python installed. Verify normal downloads, persistence, browser bridge, Plugin Manager, and a plugin install/enable/disable cycle. If PyInstaller reports a missing module or Qt plugin, adjust the build spec/hidden imports based on the actual traceback; do not assume a build succeeded just because PyInstaller created an EXE.

**Important:** Rebuild both executables whenever the plugin SDK/worker code changes. Keep `fdmx_plugin_worker.exe` next to `FDMX.exe`; do not rename or remove it. The worker is a helper process, not a second application users should launch manually.

## Create a Windows setup installer (Setup.exe)

An EXE and an installer are different deliverables:

- **Portable EXE:** the user runs `FDMX.exe` from a folder; the worker executable must remain beside it.
- **Setup installer:** a setup package copies both executables and any required resources into Program Files, creates shortcuts, and optionally registers an uninstaller.

The repository does **not yet contain a maintained Inno Setup script or a published Setup.exe**. After successfully building and testing the two executables above, install [Inno Setup](https://jrsoftware.org/isinfo.php), create an installer script that includes both files, and compile it. The installer must install `FDMX.exe` and `fdmx_plugin_worker.exe` into the same application directory. Keep user data in the user's profile (for example `%USERPROFILE%\.fdmx`), not inside Program Files, so updates and uninstalling the application do not unexpectedly erase download history or plugin data.

Do not distribute a setup package until it has been tested on a clean Windows machine, including install, launch, upgrade, uninstall, and preservation of user data.

## Browser extensions

The extension sources are under `browser-extensions/`. Load them in developer mode for testing:

**Chrome**
1. Start FDMX.
2. Open `chrome://extensions`.
3. Enable Developer mode.
4. Select **Load unpacked** and choose `browser-extensions/chrome`.

**Firefox**
1. Start FDMX.
2. Open `about:debugging#/runtime/this-firefox`.
3. Select **Load Temporary Add-on**.
4. Choose `browser-extensions/firefox/manifest.json`.

The desktop bridge uses loopback networking at `127.0.0.1:38471`. It is intended for the same computer only; do not expose it on a LAN or public interface. Firefox temporary add-ons are removed when Firefox closes; permanent distribution requires Mozilla signing.

## Plugin system and security notes

The plugin platform includes manifest/permission validation, separate worker-process execution, plugin settings/data, Ed25519 package signatures, local publisher trust, HTTPS repository metadata, update history, and rollback support.

- Newly installed or updated plugins are not automatically started.
- Invalid signatures are rejected.
- Publisher fingerprints should be verified through an independent trusted channel before trusting a publisher.
- A separate process is **not** an OS security sandbox. A plugin still runs with the current user's operating-system permissions. Install only plugins from sources you trust.
- See [PLUGIN_SDK.md](PLUGIN_SDK.md) for package format, signing, repository catalog, rollback, and worker build details.

## Automated Windows packaging

The workflow `.github/workflows/build-fdmx-windows.yml` builds the Windows application and plugin worker, smoke-tests the packaged worker, compiles the Inno Setup installer, and uploads a 14-day GitHub Actions artifact containing `FDMX.exe`, `fdmx_plugin_worker.exe`, `FDMX-Portable-v6.36-Windows-x64.zip`, and `FDMX-Setup-6.36.exe`. It runs on relevant pushes to the development branch or manually from **Actions → Build FDMX Windows packages → Run workflow**. Open the completed run and download the `FDMX-Windows-v6.36` artifact. This workflow performs packaging checks; it does not replace the separate plugin SDK integration-test matrix.

## Tests and CI

Run the SDK test suite from the repository root:

```powershell
python -m pip install PySide6 cryptography
python -m py_compile FDMX_v6_36.py fdmx_plugin_sdk.py fdmx_plugin_host.py fdmx_plugin_repository.py
python -m unittest discover -s tests -v
```

GitHub Actions includes a four-way SDK test matrix (Windows/Ubuntu × Python 3.11/3.12) and a separate plugin-worker build/smoke-test workflow. The latest SDK integration-test run on this development branch is currently failing; inspect and fix that run before declaring the SDK 1.7 work stable or publishing a release. The historical Windows build workflows target older application versions and are not a verified release pipeline for v6.36.

## Data location

Application task/history data is stored under the user's home directory in `.fdmx` (including `history.json` and `tasks.json`). Keep this user-data directory separate from the application installation directory. Download URLs can contain private tokens; remove them from logs and bug reports before sharing.

## License

The repository currently includes [LICENSE-NOTICE.md](LICENSE-NOTICE.md). Review that notice before redistributing binaries or source code; the presence of source code on GitHub does not by itself grant permission for redistribution or commercial use.
