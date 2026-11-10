"""Smoke-test a PyInstaller-built FDMX plugin worker executable."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/smoke_plugin_worker.py <worker-executable>")
    worker = Path(sys.argv[1]).resolve()
    if not worker.is_file():
        raise SystemExit(f"Worker executable not found: {worker}")
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        (folder / "plugin.py").write_text(
            "def register(api):\n    pass\n", encoding="utf-8"
        )
        process = subprocess.Popen(
            [str(worker), str(folder), "plugin.py", "ci_smoke", "[]"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace"
        )
        try:
            stdout, stderr = process.communicate(
                input=json.dumps({"type": "shutdown"}) + "\n", timeout=15
            )
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise SystemExit("Packaged worker did not exit within 15 seconds")
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            raise SystemExit(f"Worker produced no protocol response. stderr: {stderr[-2000:]}")
        try:
            first = json.loads(lines[0])
        except ValueError as exc:
            raise SystemExit(f"Worker emitted invalid JSON: {lines[0]!r}") from exc
        if first.get("type") != "ready":
            raise SystemExit(f"Worker did not become ready: {first!r}; stderr: {stderr[-2000:]}")
        if process.returncode != 0:
            raise SystemExit(f"Worker exited with {process.returncode}; stderr: {stderr[-2000:]}")
        print(f"Packaged worker smoke test passed: {worker.name}")


if __name__ == "__main__":
    main()
