"""The committed zips in dist/ must ship exactly the add-on source.

Fails when the add-on changed without `python tools/package_addon.py`, or
when a zip picked up files from somewhere else.
"""

from pathlib import Path
import importlib.util
import unittest
from zipfile import ZipFile

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("package_addon", _ROOT / "tools" / "package_addon.py")
package_addon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(package_addon)


class DistTests(unittest.TestCase):
    def test_zips_match_source(self):
        expected = package_addon.addon_files()
        for name in package_addon.ZIPS:
            path = package_addon.DIST / name
            with self.subTest(zip=name):
                self.assertTrue(path.is_file(), f"{path} is missing; run tools/package_addon.py")
                with ZipFile(path) as archive:
                    shipped = {n: archive.read(n) for n in archive.namelist()}
                self.assertEqual(sorted(shipped), sorted(expected),
                                 "zip file list is stale; run tools/package_addon.py")
                for file, data in expected.items():
                    self.assertEqual(shipped[file], data,
                                     f"{file} is stale in {name}; run tools/package_addon.py")

    def test_only_the_addon_ships(self):
        for file in package_addon.addon_files():
            self.assertTrue(file.startswith("paintify_gpu/"), file)
            self.assertTrue(file.endswith((".py", ".glsl")), file)


if __name__ == "__main__":
    unittest.main()
