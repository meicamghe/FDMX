# GNS Downloader 6.40.3

GNS Downloader is a cross-platform Python desktop download manager built with PySide6.

**فارسی:** [راهنمای فارسی نصب و استفاده](docs/README_FA.md)

## Current version

- Application version: **6.40.3**
- Main source: `FDMX_v6_36.py`
- Python version: **3.12**
- Windows packages: Windows 10/11, x64
- Linux source launch: `python ubuntu.py` (same current application source)
- Appearance: Windows 11 Fluent on Windows; Ubuntu Yaru automatically on Linux.
- There is no Theme Studio or Plugin Manager in the desktop interface.

## What's new in 6.40.3

- The updater now displays the target version and GitHub release notes before downloading, asks for confirmation, and shows live download progress with cancellation.
- Downloaded Setup files are checked against the release asset size and SHA-256 digest when provided. A separate confirmation is required before launching the installer.
- Update installation is blocked while downloads are active, and is postponed if the application cannot close safely.
- CI branch builds create temporary artifacts; permanent GitHub Releases are published only from version tags.

## Features introduced in 6.40

- **Help → Check for updates** checks the latest public GitHub Release, compares versions, downloads the Windows Setup asset, validates its size and SHA-256 digest when provided by GitHub, and offers to launch the installer.
- About dialog credits: **Created by MeysamGNS**, developed with assistance from **ChatGPT**.
- Ubuntu Yaru appearance automatically selected on Linux while preserving Windows 11 Fluent on Windows.
- Adaptive download engine measures initial throughput, selects a safe number of parts, persists byte-range maps for resume, and falls back to one stream when HTTP Range is unavailable.
- Per-download details switch to **Open** and **Close** after successful completion.

The adaptive engine keeps a stable part layout during each transfer so pause/resume does not mix byte ranges. It does not dynamically repartition a running download.

## Windows downloads

Release assets for v6.40.3:

- **[Portable ZIP — v6.40.3](https://github.com/meicamghe/FDMX/releases/download/v6.40.3/GNS-Downloader-Portable-Windows-x64.zip)** — extract and run `GNS Downloader.exe`.
- **[Setup installer — v6.40.3](https://github.com/meicamghe/FDMX/releases/download/v6.40.3/GNS-Downloader-Setup.exe)** — installs the application and shortcuts.
- [All GitHub Releases](https://github.com/meicamghe/FDMX/releases)

The in-app installer update is for the installed Windows build. Portable and source-based copies open the release page so you can replace the folder with the new Portable ZIP.

Release workflow: [Build GNS Downloader Windows packages](https://github.com/meicamghe/FDMX/actions/workflows/build-fdmx-windows.yml). The [v6.40.3 release](https://github.com/meicamghe/FDMX/releases/tag/v6.40.3) contains the Windows packages and Linux DEB package. Branch builds create CI artifacts; version-tag builds publish release assets.



## Linux installation (Ubuntu and Debian)

A native **Ubuntu/Debian `.deb` package** is now built by the Linux GitHub Actions workflow for version 6.40.3. The package is generated as a CI artifact on pull requests and branch builds; it is attached to the public GitHub Release when the matching version tag is published. An AppImage or Flatpak is not provided yet. You do **not** need Wine. The Linux build uses the same maintained application source and selects the Ubuntu Yaru appearance automatically.

1. Install the Qt runtime libraries (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y git libegl1 libgl1 libxkbcommon0 libdbus-1-3
```

2. Make sure **Python 3.12** is installed. This is the Python version used by the project CI. Check it with:

```bash
python3.12 --version
```

If the command is missing, install Python 3.12 and its `venv` support using the package source appropriate for your Linux distribution before continuing.

3. Download the source and create an isolated environment:

```bash
git clone https://github.com/meicamghe/FDMX.git
cd FDMX
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials
```

4. Start the application:

```bash
python ubuntu.py
```

You can also launch the maintained source directly with `python FDMX_v6_36.py`. Run these commands from the project directory and activate `.venv` again after opening a new terminal:

```bash
cd FDMX
source .venv/bin/activate
python ubuntu.py
```

**Troubleshooting:** If Qt reports that the `xcb` platform plugin or a shared library is missing, install the additional Ubuntu/Debian Qt XCB libraries and retry:

```bash
sudo apt install -y libxcb-cursor0 libxcb-xinerama0 libxcb-icccm4 libxcb-keysyms1 libxcb-render-util0
```

If the window does not appear, make sure you are running inside a graphical desktop session (not a text-only SSH session). For a clean reinstall of Python dependencies, run `python -m pip install --force-reinstall PySide6-Essentials` while the virtual environment is active.

## Run from source on Windows

Install **Python 3.12** and the application dependency:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials
python FDMX_v6_36.py
```

## Build Windows packages

Windows executables are built on Windows (PyInstaller is not a cross-compiler). Use Python 3.12, PySide6-Essentials, PyInstaller, Pillow and Inno Setup. The reproducible build and smoke tests are defined in [the GitHub Actions workflow](.github/workflows/build-fdmx-windows.yml).

## Browser extensions and privacy

Chrome and Firefox extension sources are in `browser-extensions/`. The desktop bridge listens only on `127.0.0.1:38471`; do not expose it on a LAN or public interface.

Task state and download history are stored under the user's home directory in `.fdmx`. Download URLs can contain private tokens; remove them from logs and bug reports before sharing.

## Tests

```bash
python -m py_compile FDMX_v6_36.py ubuntu.py
python tests/test_gns_downloader_regressions.py
```

Older numbered scripts remain in the repository for development history; they are not the current application entry point.

Review [LICENSE-NOTICE.md](LICENSE-NOTICE.md) before redistributing source or binaries.
