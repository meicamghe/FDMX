# GNS Downloader 6.52

GNS Downloader is a cross-platform Python desktop download manager built with PySide6.

**فارسی:** [راهنمای فارسی نصب و استفاده](docs/README_FA.md)


## Browser extensions — GNS Downloader 1.3.0

<details>
<summary><strong>Download Firefox / Chrome extensions</strong></summary>

The browser companion package is available from the successful GitHub Actions build:

- **[Download browser extensions 1.3.0 (ZIP)](https://github.com/meicamghe/FDMX/actions/runs/45807544405)** — open the run and download the `GNS-Downloader-browser-extensions-1.3.0` artifact.
- **[Firefox Add-ons submission portal](https://addons.mozilla.org/developers/)** — upload `GNS-Downloader-Firefox-1.3.0.xpi` as an update to the existing [GNS Download Manager listing](https://addons.mozilla.org/en-US/firefox/addon/gns-download-manager/). Keep the existing add-on listing/ID; do not submit it as a new add-on.
- **[Chrome installation guide](https://github.com/meicamghe/FDMX#browser-extensions-and-privacy)** — extract the Chrome ZIP, open `chrome://extensions`, enable Developer mode, then choose **Load unpacked**.

Firefox public installation/update becomes available after Mozilla review and signing. Until then, test the XPI using `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on**.

</details>


## Current version

- Application version: **6.52**
- Main source: `FDMX_v6_50.py`
- Python version: **3.12**
- Windows packages: Windows 10/11, x64
- Linux source launch: `python ubuntu.py` (same current application source)
- Appearance: Windows 11 Fluent on Windows; Ubuntu Yaru automatically on Linux.
- There is no Theme Studio or Plugin Manager in the desktop interface.

## What's new in 6.52

- GitHub Actions artifact downloads now try anonymous access first; a token is requested only after GitHub denies access.
- GitHub credentials are not written to task or history files, and authorization is removed on cross-origin redirects.
- Completed downloads are sorted newest-first, and the first Start action launches the transfer automatically.

GNS Downloader **v6.52** is the latest official public release. The maintained application source is `FDMX_v6_50.py`.

## Browser integration — 6.53 development

The current development branch adds a browser companion extension update (1.3.0) and the matching desktop bridge (6.53):

- Direct file links and browser downloads are automatically handed to GNS Downloader. If the desktop app is closed, the registered `gnsdownloader://` protocol launches it and queues the URL.
- Right-click links in Chrome or Firefox and choose **Download with GDM**; the extension icon is included.
- Pages exposing direct audio/video URLs show a media prompt. YouTube pages ask the desktop `yt-dlp` engine for available video resolutions and audio bitrates, including audio-only.
- **Tools → Install browser extensions…** in the desktop app explains Firefox AMO installation and Chrome Developer mode / Load unpacked installation.
- The existing Firefox AMO listing and Gecko ID (`fdmx-browser@gns.local`) are retained for an in-place update.

The 6.53 work is under review in [PR #33](https://github.com/meicamghe/FDMX/pull/33); it is not the public release yet. The latest public desktop release remains 6.52. The 1.3.0 browser package is produced by the [browser-extension CI workflow](https://github.com/meicamghe/FDMX/actions/workflows/build-browser-extensions.yml).

### Install Chrome extension (development build)

1. Open the [browser-extension Actions workflow](https://github.com/meicamghe/FDMX/actions/workflows/build-browser-extensions.yml) and download the latest successful `GNS-Downloader-browser-extensions-1.3.0` artifact.
2. Extract the artifact ZIP, then extract `GNS-Downloader-Chrome-1.3.0.zip`.
3. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select the extracted Chrome extension folder containing `manifest.json`.

### Install or update Firefox

Use the [GNS Download Manager AMO listing](https://addons.mozilla.org/en-US/firefox/addon/gns-download-manager/). The 1.3.0 XPI is intended as an update to that same listing; temporary Developer Edition testing is available through `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on**.


- YouTube video and audio downloads use the optional `yt-dlp` runtime. Best-quality video merging requires FFmpeg; audio-only downloads do not.
- Download proxy support includes HTTP, HTTPS, SOCKS4, SOCKS4a, SOCKS5 and SOCKS5h. SOCKS support is bundled through PySocks in the packaged build. Proxy entries require a hostname and port; endpoint paths, query strings and fragments are rejected instead of silently ignored.
- The updater checks published stable releases, selects the highest valid numeric version tag, verifies installer size and a GitHub SHA-256 digest when available, and supports canceling an in-progress installer download.
- Portable/source builds open the release page; automatic Setup installation is intended for the installed Windows build.

The v6.52 Windows installer, portable ZIP and Ubuntu/Debian package are built and smoke-tested by CI. Offline regression tests do not replace live YouTube/proxy network tests or manual GUI testing.

## What's new in 6.42

- Corrected line-break rendering in GitHub release notes shown by the in-app updater, with a useful fallback when notes are empty.
- Fixed the Windows installer icon path so the generated application icon is resolved reliably during setup compilation.
- Carries forward the 6.41 download engine, configurable part counts, and safer resume behavior.

## What's new in 6.41

- New downloads use a fixed **8-part** layout by default; the setting allows **1–16 parts** per file. Adaptive speed probing and automatic part selection have been removed.
- Existing partial downloads keep their saved byte-range layout, so changing the setting does not corrupt resume data.
- The updater shows the target version and release notes and asks once before downloading. After download and integrity verification, installation starts without a second confirmation.
- The Linux application icon and the in-app icon now share the white tile and red G branding.
- CI branch builds create temporary artifacts; permanent GitHub Releases are published only from version tags.

## Features introduced in 6.40 (historical)

- **Help → Check for updates** checks the latest public GitHub Release, compares versions, downloads the Windows Setup asset, validates its size and SHA-256 digest when provided by GitHub, and offers to launch the installer.
- About dialog credits: **Created by MeysamGNS**, developed with assistance from **ChatGPT**.
- Ubuntu Yaru appearance automatically selected on Linux while preserving Windows 11 Fluent on Windows.
- The earlier adaptive download engine has been replaced in 6.41 by predictable, user-configurable fixed part counts.
- Per-download details switch to **Open** and **Close** after successful completion.

The download engine preserves each task's original byte-range map across pause/resume.

## Windows downloads

The official v6.52 release is published. Download the files:

- **[Portable ZIP — v6.52](https://github.com/meicamghe/FDMX/releases/download/v6.52/GNS-Downloader-Portable-Windows-x64.zip)** — extract and run `GNS Downloader.exe`.
- **[Setup installer — v6.52](https://github.com/meicamghe/FDMX/releases/download/v6.52/GNS-Downloader-Setup.exe)** — installs the application and shortcuts.
- **[Ubuntu/Debian DEB — v6.52](https://github.com/meicamghe/FDMX/releases/download/v6.52/GNS-Downloader-6.52-amd64.deb)** — AMD64 package.
- [All GitHub Releases](https://github.com/meicamghe/FDMX/releases)

The in-app installer update is for the installed Windows build. Portable and source-based copies open the release page so you can replace the folder with the new Portable ZIP.

Release workflow: [Publish GNS Downloader v6.52](https://github.com/meicamghe/FDMX/actions/workflows/publish-release-v6-50.yml). The published release is [GNS Downloader v6.52](https://github.com/meicamghe/FDMX/releases/tag/v6.52), with Windows installer, portable ZIP and Linux DEB assets.



## Linux installation (Ubuntu and Debian)

A native **Ubuntu/Debian `.deb` package** for version 6.52 has been built, smoke-tested, and attached to the public GitHub Release. An AppImage or Flatpak is not provided yet. You do **not** need Wine. The Linux build uses the same maintained application source and selects the Ubuntu Yaru appearance automatically.

### Quick install: official Linux package

The v6.52 release includes a ready-to-install **AMD64 `.deb` package**. This is the recommended route for normal use; it does not require Git, Python, a virtual environment, or Wine.

Check the system architecture (it should print `amd64`):

```bash
dpkg --print-architecture
```

Download and install the package (APT will resolve its declared system dependencies):

```bash
curl -fL "https://github.com/meicamghe/FDMX/releases/download/v6.52/GNS-Downloader-6.52-amd64.deb" -o /tmp/GNS-Downloader-6.52-amd64.deb
sudo apt install /tmp/GNS-Downloader-6.52-amd64.deb
```

Launch **GNS Downloader** from the desktop application menu, or run `gns-downloader` in a terminal. The package is built and smoke-tested on Ubuntu 22.04 AMD64. AppImage and Flatpak are not provided yet.

### Alternative: run from source (requires Git and Python 3.12)

1. Install the Qt runtime libraries (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y git libegl1 libgl1 libxkbcommon0 libdbus-1-3
```

2. Make sure **Python 3.12** is installed. This is the Python version used by the project CI. Check it with:

```bash
python3.12 --version
```

If Python 3.12 is missing, install it for your distribution:

**Ubuntu 24.04 LTS** (available in the standard repositories):

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip
```

**Ubuntu 22.04 or Debian 12:** the standard repositories do not provide Python 3.12 as the default interpreter. Install the standalone Python manager `uv`, then download Python 3.12:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

If `uv` is not found, open a new terminal.

3. Download the source and create an isolated environment:

```bash
git clone https://github.com/meicamghe/FDMX.git
cd FDMX
```

On Ubuntu 24.04, create the environment with:

```bash
python3.12 -m venv .venv
```

On Ubuntu 22.04 or Debian 12, use:

```bash
uv venv --python 3.12 --seed .venv
```

Then activate the environment and install the application dependency:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials yt-dlp PySocks
```

4. Start the application:

```bash
python ubuntu.py
```

You can also launch the maintained source directly with `python FDMX_v6_50.py`. Run these commands from the project directory and activate `.venv` again after opening a new terminal:

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
python -m pip install PySide6-Essentials yt-dlp PySocks
python FDMX_v6_50.py
```

## Build Windows packages

Windows executables are built on Windows (PyInstaller is not a cross-compiler). Use Python 3.12, PySide6-Essentials, PyInstaller, Pillow and Inno Setup. The reproducible build and smoke tests are defined in [the GitHub Actions workflow](.github/workflows/build-fdmx-windows.yml).

## Browser extensions and privacy

Chrome and Firefox extension sources are in `browser-extensions/`. The desktop bridge listens only on `127.0.0.1:38471`; do not expose it on a LAN or public interface.

Task state and download history are stored under the user's home directory in `.fdmx`. Download URLs can contain private tokens; remove them from logs and bug reports before sharing.

## Tests

```bash
python -m py_compile FDMX_v6_50.py ubuntu.py
python -m unittest discover -s tests -p "test_youtube_integration_regressions.py" -v
```

Older numbered scripts remain in the repository for development history; they are not the current application entry point.

Review [LICENSE-NOTICE.md](LICENSE-NOTICE.md) before redistributing source or binaries.
