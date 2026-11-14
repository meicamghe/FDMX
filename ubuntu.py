"""Compatibility launcher for the current GNS Downloader Linux build.

The maintained application source is FDMX_v6_50.py. It selects the Ubuntu Yaru
appearance automatically on Linux; this wrapper prevents a duplicate legacy
application from drifting away from the current version.
"""
from pathlib import Path
import runpy


if __name__ == "__main__":
    application = Path(__file__).with_name("FDMX_v6_50.py")
    runpy.run_path(str(application), run_name="__main__")
