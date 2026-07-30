from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from sync_codex_assets import compare_tree, ignored_runtime_path, parse_mode  # noqa: E402


class SyncCodexAssetsTests(unittest.TestCase):
    def test_parse_mode_requires_explicit_runtime_drift_override(self) -> None:
        self.assertEqual(parse_mode([]), "sync")
        self.assertEqual(parse_mode(["--check"]), "check")
        self.assertEqual(
            parse_mode(["--overwrite-runtime-drift"]),
            "overwrite",
        )
        with self.assertRaisesRegex(ValueError, "usage"):
            parse_mode(["--force"])

    def test_compare_tree_detects_managed_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "SKILL.md").write_text("source\n", encoding="utf-8")
            (target / "SKILL.md").write_text("source\n", encoding="utf-8")
            self.assertEqual(compare_tree(source, target, "skill/demo"), [])

            (target / "SKILL.md").write_text("runtime edit\n", encoding="utf-8")
            drift = compare_tree(source, target, "skill/demo")
            self.assertEqual(len(drift), 1)
            self.assertIn("content differs", drift[0].label)
            self.assertTrue(drift[0].target_exists)

    def test_runtime_caches_are_not_managed_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            target.mkdir()
            (source / "SKILL.md").write_text("same\n", encoding="utf-8")
            (target / "SKILL.md").write_text("same\n", encoding="utf-8")
            cache = target / "__pycache__"
            cache.mkdir()
            (cache / "dbctl.cpython-312.pyc").write_bytes(b"runtime-cache")
            (target / ".DS_Store").write_bytes(b"metadata")

            self.assertTrue(ignored_runtime_path(Path("__pycache__/x.pyc")))
            self.assertTrue(ignored_runtime_path(Path(".DS_Store")))
            self.assertEqual(compare_tree(source, target, "skill/demo"), [])


if __name__ == "__main__":
    unittest.main()
