#!/usr/bin/env python3
"""Stage only Qt QML modules reported by PySide6's import scanner."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def parse_imports(output: str) -> list[str]:
    """Return unique Qt module names from qmlimportscanner JSON output."""
    start = output.find("[")
    end = output.rfind("]")
    if start < 0 or end < start:
        raise ValueError("qmlimportscanner did not emit a JSON array")
    payload = json.loads(output[start : end + 1])
    if not isinstance(payload, list):
        raise ValueError("qmlimportscanner output must be a JSON array")
    names = {
        item["name"]
        for item in payload
        if isinstance(item, dict)
        and item.get("type") == "module"
        and isinstance(item.get("name"), str)
        and item["name"].startswith("Qt")
    }
    if not names:
        raise ValueError("qmlimportscanner found no Qt QML modules")
    return sorted(names)


def _module_path(root: Path, name: str) -> Path:
    return root.joinpath(*name.split("."))


def stage_modules(import_root: Path, output_root: Path, module_names: Iterable[str]) -> list[str]:
    """Copy selected modules while excluding unselected nested QML modules."""
    import_root = import_root.resolve(strict=True)
    selected = set(module_names)
    if not selected:
        raise ValueError("No QML modules were selected")
    for name in selected:
        if not name.startswith("Qt") or any(part in ("", ".", "..") for part in name.split(".")):
            raise ValueError(f"Invalid Qt QML module name: {name!r}")
        source = _module_path(import_root, name)
        if not source.is_dir() or not (source / "qmldir").is_file():
            raise FileNotFoundError(f"QML module {name!r} was not found at {source}")

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    def ignore_unselected_nested_modules(directory: str, entries: list[str]) -> set[str]:
        current = Path(directory)
        ignored: set[str] = set()
        for entry in entries:
            candidate = current / entry
            if not candidate.is_dir() or not (candidate / "qmldir").is_file():
                continue
            try:
                relative = candidate.relative_to(import_root)
            except ValueError:
                continue
            nested_name = ".".join(relative.parts)
            if nested_name.startswith("Qt") and nested_name not in selected:
                ignored.add(entry)
        return ignored

    for name in sorted(selected, key=lambda value: (value.count("."), value)):
        source = _module_path(import_root, name)
        destination = _module_path(output_root, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=ignore_unselected_nested_modules,
        )
    return sorted(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qml-root", type=Path, required=True)
    parser.add_argument("--import-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    scanner = shutil.which("pyside6-qmlimportscanner")
    if scanner is None:
        scanner = shutil.which("pyside6-qmlimportscanner.exe")
    if scanner is None:
        print("pyside6-qmlimportscanner was not found on PATH", file=sys.stderr)
        return 2

    command = [scanner, "-rootPath", str(args.qml_root.resolve())]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode:
        print(completed.stdout, file=sys.stderr)
        print(completed.stderr, file=sys.stderr)
        return completed.returncode
    try:
        modules = parse_imports(completed.stdout)
        staged = stage_modules(args.import_root, args.output, modules)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"QML runtime staging failed: {exc}", file=sys.stderr)
        return 1

    print("Staged Qt QML modules:")
    for name in staged:
        print(f"  - {name}")
    total = sum(path.stat().st_size for path in args.output.rglob("*") if path.is_file())
    print(f"Staged QML runtime: {total / (1024 * 1024):.2f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
