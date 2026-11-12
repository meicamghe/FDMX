# GNS Downloader 6.40.2

GNS Downloader is a cross-platform Python desktop download manager built with PySide6.

**فارسی:** [راهنمای فارسی نصب و استفاده](docs/README_FA.md)

## Current version

- Application version: **6.40.2**
- Main source: `FDMX_v6_36.py`
- Python version: **3.12**
- Windows packages: Windows 10/11, x64
- Linux source launch: `python ubuntu.py` (same current application source)
- Appearance: Windows 11 Fluent on Windows; Ubuntu Yaru automatically on Linux.
- There is no Theme Studio or Plugin Manager in the desktop interface.

## What's new in 6.40.2

- Version metadata is now aligned across the application, Windows installer, and release packages. This fixes the repeated-update offer that occurred when the installed app reported an older version than the release tag.
- [Release v6.40.2](https://github.com/meicamghe/FDMX/releases/tag/v6.40.2) was published on 2026-11-11. The Windows Setup and Portable ZIP assets are available below.

## Features introduced in 6.40

- **Help → Check for updates** checks the latest public GitHub Release, compares versions, downloads the Windows Setup asset, validates its size and SHA-256 digest when provided by GitHub, and offers to launch the installer.
- About dialog credits: **Created by MeysamGNS**, developed with assistance from **ChatGPT**.
- Ubuntu Yaru appearance automatically selected on Linux while preserving Windows 11 Fluent on Windows.
- Adaptive download engine measures initial throughput, selects a safe number of parts, persists byte-range maps for resume, and falls back to one stream when HTTP Range is unavailable.
- Per-download details switch to **Open** and **Close** after successful completion.

The adaptive engine keeps a stable part layout during each transfer so pause/resume does not mix byte ranges. It does not dynamically repartition a running download.

## Windows downloads

Permanent release links (updated when a new stable release is published):

- **[Portable ZIP — v6.40.2](https://github.com/meicamghe/FDMX/releases/download/v6.40.2/GNS-Downloader-Portable-Windows-x64.zip)** — extract and run `GNS Downloader.exe`.
- **[Setup installer — v6.40.2](https://github.com/meicamghe/FDMX/releases/download/v6.40.2/GNS-Downloader-Setup.exe)** — installs the application and shortcuts.
- [All GitHub Releases](https://github.com/meicamghe/FDMX/releases)

The in-app installer update is for the installed Windows build. Portable and source-based copies open the release page so you can replace the folder with the new Portable ZIP.

Release workflow: [Build GNS Downloader Windows packages](https://github.com/meicamghe/FDMX/actions/workflows/build-fdmx-windows.yml). The current stable release is [v6.40.2](https://github.com/meicamghe/FDMX/releases/tag/v6.40.2). Branch builds create CI artifacts; version-tag builds publish release assets.

The next updater UX improvement (release notes and version shown before download, explicit download/install confirmations, and live download progress) is tracked in [PR #18](https://github.com/meicamghe/FDMX/pull/18). It is not included in the already-published v6.40.2 installer.

## Run from source

Install **Python 3.12** and the application dependency:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials
python FDMX_v6_36.py
```

On Linux, the compatibility launcher is also available:

```bash
python ubuntu.py
```

On Windows PowerShell:

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
