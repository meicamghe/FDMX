# FDMX — Download Manager

**FDMX** is a Python desktop download manager built with **PySide6**. [راهنمای فارسی نصب و استفاده](docs/README_FA.md) is also available. The project includes a Windows-focused desktop application, an Ubuntu-themed interface variant, and browser extensions for Chrome and Firefox.

> Project status: actively developed. Some capabilities and browser-integration workflows may depend on the selected script version. This repository currently contains multiple historical builds; for the latest tested Windows build use **FDMX_v6_11.py**. The Ubuntu-themed build is **ubuntu.py** and should be treated as experimental until tested on your system.

## Highlights

- Multi-connection HTTP/HTTPS downloads with configurable connection count.
- Pause, resume, cancel and retry controls.
- Per-download details window with progress and transfer information.
- Download history and task persistence between application sessions.
- Download scheduling with date and time controls.
- Clipboard URL support and browser hand-off through local loopback bridge.
- Speed limiting and download destination selection.
- Categorization of common file types.
- Chrome and Firefox extensions for sending links to FDMX.
- Ubuntu-inspired aubergine and orange interface in `ubuntu.py`.

Feature availability can differ between builds. Torrent support and media URL scanning are experimental and may have limitations; DRM-protected streams and browser blob URLs are not guaranteed to work.

## Repository layout

| Path | Description |
|---|---|
| `FDMX_v6_11.py` | Latest tested Windows desktop build |
| `ubuntu.py` | Ubuntu-themed UI variant; experimental |
| `FDMX_v6_*.py` | Earlier development builds kept for reference |
| `browser-extensions/chrome/` | Chrome extension source |
| `browser-extensions/firefox/` | Firefox extension source |
| `browser-extensions/README.md` | Browser extension installation notes |

## Requirements

- Windows 10/11 (primary tested environment); Ubuntu/Linux may work with the Ubuntu variant but is not yet fully validated.
- Python 3.10 or newer.
- PySide6.
- Internet access for downloading files and installing Python packages.

The desktop script uses Python standard-library modules plus PySide6; no separate third-party downloader package is required by the current source.

## Install and run on Windows

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/). During setup, enable **Add Python to PATH**.
2. Download this repository using **Code → Download ZIP**, then extract it; or clone it:

   ```powershell
   git clone https://github.com/meicamghe/FDMX.git
   cd FDMX
   ```

3. (Recommended) Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use Command Prompt:

   ```bat
   .venv\Scripts\activate.bat
   ```

4. Install the UI dependency:

   ```powershell
   py -m pip install --upgrade pip
   py -m pip install PySide6
   ```

5. Run the tested Windows build:

   ```powershell
   py FDMX_v6_11.py
   ```

   To try the Ubuntu-themed variant on Windows:

   ```powershell
   py ubuntu.py
   ```

## Run on Ubuntu / Linux

The Ubuntu-themed script is provided as a development build, not a promise of full Linux compatibility.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
git clone https://github.com/meicamghe/FDMX.git
cd FDMX
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6
python ubuntu.py
```

If the virtual environment cannot access system Qt libraries or the display server, check the PySide6 installation and your desktop environment. See the [official Qt for Python getting-started guide](https://doc.qt.io/qtforpython-6/quickstart.html).

## Using FDMX

1. Start the application.
2. Paste an HTTP or HTTPS download URL into the URL field (or use the clipboard feature if available in that build).
3. Choose the destination folder and adjust connection/speed options as needed.
4. Start the download.
5. Open a download's details window to inspect progress and use Pause, Resume, Cancel or Retry when available.
6. Use the scheduling section to configure a future start time. Keep the application running for scheduled tasks to execute.

Downloads depend on the remote server. Some servers block parallel connections, require authentication, expire signed URLs, or do not support resuming. In those cases, a download may use fewer connections or need to be restarted.

## Browser integration

The browser extensions communicate with the desktop application through a local-only bridge at **127.0.0.1:38471**.

### Chrome

1. Start the FDMX desktop application with browser bridge support.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Click **Load unpacked**.
5. Select the repository folder `browser-extensions/chrome`.
6. Right-click a link and choose **Download link with FDMX**, or open the extension popup and send the current page URL.

### Firefox

1. Start the FDMX desktop application with browser bridge support.
2. Open `about:debugging#/runtime/this-firefox`.
3. Click **Load Temporary Add-on**.
4. Select `browser-extensions/firefox/manifest.json`.
5. Right-click a link and choose **Download link with FDMX**, or use the popup.

Firefox temporary add-ons are removed when Firefox closes. Permanent distribution requires Mozilla review/signing. An unsigned XPI normally cannot be installed permanently in standard Firefox release builds.

### Browser connection troubleshooting

- Confirm FDMX is running before sending a URL.
- The local bridge listens on `127.0.0.1:38471`; it is not intended to be exposed to the LAN or public internet.
- If the extension reports that it cannot connect, verify that the desktop build includes the bridge and that the port is not blocked or occupied.
- Do not change the bridge to listen on `0.0.0.0` or expose it publicly.

## Data and privacy

FDMX stores local task/history data under the user's home directory in `.fdmx` (including `history.json` and `tasks.json`). Browser integration uses loopback networking on the same computer. Download URLs may contain private tokens; avoid sharing logs, screenshots, or exported task files that expose signed URLs.

## Troubleshooting

| Problem | Things to check |
|---|---|
| `No module named PySide6` | Activate the environment and run `py -m pip install PySide6`. |
| App does not start | Run it from PowerShell/Terminal and copy the full traceback. |
| Browser says it cannot connect | Start FDMX first; verify local bridge support and port 38471. |
| Download stops or cannot resume | The server may not support byte ranges, or the URL may have expired. |
| Firefox says the add-on is unverified | Use temporary loading for testing, or submit it to Mozilla for signing. |

## Development notes

- Main application: Python + PySide6 (Qt Widgets).
- Networking and HTTP handling use Python's standard library.
- Please report reproducible bugs with OS version, Python version, selected script/build, steps to reproduce, and the full error output. Remove credentials and private URL tokens before posting.
- Contributions and feature suggestions are welcome through GitHub Issues.

## Roadmap

- Consolidate historical scripts into a cleaner package structure.
- Add automated tests for download workers and browser bridge.
- Publish versioned releases and signed browser packages.
- Improve Linux testing and packaging.
- Document supported torrent and media-download workflows once they are stable.

## License

The repository does not currently grant an open-source license. See [LICENSE-NOTICE.md](LICENSE-NOTICE.md). Viewing the source does not by itself grant permission to redistribute, modify, or use it commercially.

## Acknowledgements

Built with Python and [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/).
