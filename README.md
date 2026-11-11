# GNS Downloader 6.38

GNS Downloader is a Windows desktop download manager built with Python and PySide6.

**فارسی:** [راهنمای فارسی نصب و استفاده](docs/README_FA.md)

## Current build

- Application version: **6.38**
- Main source: `FDMX_v6_36.py`
- Primary target: Windows 10/11, x64
- Interface: fixed Windows 11 Fluent appearance. There is no theme-selection tab or Theme Studio.
- The desktop application UI does not include a Plugin Manager.

## Features

- HTTP/HTTPS downloads with multi-connection transfers.
- Pause, resume, cancel, retry, queue management and persistent task state.
- Per-download details window with progress and segment information.
- Scheduling, speed limits, download history and CSV/JSON analytics.
- Browser hand-off through a local-only bridge at `127.0.0.1:38471`.
- Per-download post-completion action: do nothing, shut down Windows, log out, or hibernate. The action is configured in that download's own details window and does not affect other downloads.
- Enabled and disabled buttons use distinct visual treatments.

Post-completion power actions are Windows-only and run only after a successful completion. Use them carefully; shutdown, log out and hibernate can interrupt other work.

## Download the Windows packages

The CI workflow publishes two separate artifacts after a successful build:

- **[Portable ZIP — GNS Downloader 6.38](https://github.com/meicamghe/FDMX/actions)** — extract the ZIP and run `GNS Downloader.exe`.
- **[Setup installer — GNS Downloader 6.38](https://github.com/meicamghe/FDMX/actions)** — run Setup to install the application and create shortcuts.

Open the latest successful **Build GNS Downloader Windows packages** run in GitHub Actions and download the matching artifact. Artifacts are retained for 14 days. These are CI artifacts, not a permanent GitHub Release.

## Run from source on Windows

Install Python 3.12, then run in PowerShell from the repository directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials
python FDMX_v6_36.py
```

## Build packages locally

The Windows packages are built on Windows (PyInstaller is not a cross-compiler). Install Python 3.12, PySide6-Essentials, PyInstaller, Pillow and Inno Setup, then use the same build workflow as the source of truth:

1. Generate the icon: `python installer/create_icon.py`
2. Build the onedir app with PyInstaller.
3. Compile `installer/FDMX.iss` with Inno Setup.
4. Zip the contents of `dist/GNS Downloader` for the portable package.

For repeatable builds and smoke testing, prefer GitHub Actions → **Build GNS Downloader Windows packages**.

## Browser extensions

Chrome and Firefox extension sources are in `browser-extensions/`. The desktop bridge listens only on `127.0.0.1:38471`; do not expose it on a LAN or public interface. Firefox temporary add-ons must be loaded again after the browser closes.

## Data and privacy

Task state and download history are stored under the user's home directory in `.fdmx`. Download URLs can contain private tokens; remove them from logs and bug reports before sharing.

## Tests

Run the focused application regression checks from the repository root:

```powershell
python -m py_compile FDMX_v6_36.py
python tests/test_gns_downloader_regressions.py
```

## Repository notes

Older numbered scripts and the separate Plugin SDK development files remain in the repository for history and development. They are not the current GNS Downloader desktop entry point or part of the packaged application.

Review [LICENSE-NOTICE.md](LICENSE-NOTICE.md) before redistributing source or binaries.
