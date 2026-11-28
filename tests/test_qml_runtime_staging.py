import json
import tempfile
import unittest
from pathlib import Path

from scripts.stage_qml_runtime import parse_imports, stage_modules


class QmlRuntimeStagingTests(unittest.TestCase):
    def test_parse_imports_keeps_unique_qt_modules_only(self):
        payload = [
            {"name": "QtQuick", "type": "module"},
            {"name": "QtQuick.Controls", "type": "module"},
            {"name": "QtQuick", "type": "module"},
            {"name": "LocalModule", "type": "module"},
            {"name": "QtQuick.Controls", "type": "plugin"},
        ]
        self.assertEqual(
            parse_imports(json.dumps(payload)),
            ["QtQuick", "QtQuick.Controls"],
        )

    def test_stage_includes_selected_nested_modules_and_excludes_others(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            imports = root / "imports"
            output = root / "staged"
            for module in (
                "QtQuick",
                "QtQuick.Controls",
                "QtQuick.Controls.Basic",
                "QtQuick.Controls.Fusion",
                "QtQuick.Layouts",
            ):
                directory = imports.joinpath(*module.split("."))
                directory.mkdir(parents=True)
                (directory / "qmldir").write_text("module " + module, encoding="utf-8")
                (directory / "plugin.dll").write_bytes(b"plugin")
            staged = stage_modules(
                imports,
                output,
                ["QtQuick", "QtQuick.Controls", "QtQuick.Controls.Basic"],
            )
            self.assertEqual(
                staged,
                ["QtQuick", "QtQuick.Controls", "QtQuick.Controls.Basic"],
            )
            self.assertTrue((output / "QtQuick" / "qmldir").is_file())
            self.assertTrue((output / "QtQuick" / "Controls" / "Basic" / "plugin.dll").is_file())
            self.assertFalse((output / "QtQuick" / "Controls" / "Fusion").exists())
            self.assertFalse((output / "QtQuick" / "Layouts").exists())

    def test_missing_module_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            imports = root / "imports"
            imports.mkdir()
            with self.assertRaises(FileNotFoundError):
                stage_modules(imports, root / "out", ["QtQuick"])


if __name__ == "__main__":
    unittest.main()
