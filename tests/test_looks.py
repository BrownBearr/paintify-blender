"""Tests for the add-on's pure-Python parts. No Blender needed."""

from pathlib import Path
import math
import sys
import types
import unittest

# Load the submodules without the package __init__, which imports bpy.
_ADDON = Path(__file__).resolve().parents[1] / "blender_addon" / "paintify_gpu"
_package = types.ModuleType("paintify_gpu")
_package.__path__ = [str(_ADDON)]
sys.modules.setdefault("paintify_gpu", _package)

from paintify_gpu import brushes, looks  # noqa: E402


class BrushTileTests(unittest.TestCase):
    def test_matches_paintify_gpu(self):
        # Values printed by paintify-GPU's src/brush_atlas.cpp makeTiles({8, 4, 2}, 10).
        data, rows = brushes.make_atlas((8.0, 4.0, 2.0))
        self.assertEqual(rows, [16, 8, 8])
        self.assertEqual(len(data), 24 * brushes.TILE_W * brushes.TILE_ROWS_MAX)
        expected = {0: 0.5241359, 63: 0.5224302, 500: 0.9756446, 3071: 0.0,
                    3072: 0.0412339, 10000: 0.6409130, 71109: 0.6163301}
        for index, value in expected.items():
            self.assertAlmostEqual(data[index], value, places=6)
        self.assertAlmostEqual(sum(data), 9450.092, places=2)


class ScaleTests(unittest.TestCase):
    def test_camera_preview_matches_render(self):
        # A 50% preview of a 1200 px wide camera frame and the 1920x1080
        # render get the same stroke size relative to the frame.
        style = looks.STYLES["impressionist"]
        preview = looks.layer_radii(style, looks.stroke_scale(600, 338, 1.0))
        render = looks.layer_radii(style, looks.stroke_scale(1920, 1080, 1.0))
        for small, big in zip(preview, render):
            self.assertAlmostEqual(small / 600, big / 1920, delta=0.0005)

    def test_radii_keep_every_layer(self):
        radii = looks.layer_radii(looks.STYLES["detail"], 0.1)
        self.assertEqual(radii, (1.0, 1.0, 1.0))
        self.assertEqual(looks.layer_radii(looks.STYLES["wash"], 1.0), (20.0, 10.0))

    def test_reference_size_is_identity(self):
        self.assertAlmostEqual(looks.stroke_scale(800, 450), 1.0)
        self.assertAlmostEqual(looks.stroke_scale(800, 450, 2.0), 2.0)


class PlanTests(unittest.TestCase):
    def test_passes_cover_every_cell(self):
        for size in ((64, 36), (1920, 1080), (7680, 4320)):
            for radius in (1.0, 2.0, 7.5, 40.0):
                plan = looks.plan_layer(*size, radius, 1.0)
                self.assertGreaterEqual(plan.slots * plan.passes, plan.cells)
                self.assertLess((plan.slots - 1) * plan.passes, plan.cells)
                self.assertTrue(looks.MIN_PASSES <= plan.passes <= looks.MAX_PASSES)
                self.assertEqual(plan.cells_x, math.ceil(size[0] / plan.grid))

    def test_draw_order_is_a_permutation(self):
        for count in (1, 7, 1543, 1543 * 1549, 20000):
            step = looks.draw_order_step(count)
            self.assertEqual(math.gcd(step, count), 1)
            self.assertLess(2 * 1024 * 1024 * step, 2 ** 32)
        count = 1000
        step = looks.draw_order_step(count)
        self.assertEqual(sorted(i * step % count for i in range(count)), list(range(count)))

    def test_hold_frames(self):
        self.assertEqual(looks.hold_frames(24, 12), 2)
        self.assertEqual(looks.hold_frames(30, 12), 2)
        self.assertEqual(looks.hold_frames(24, 8), 3)
        self.assertEqual(looks.hold_frames(24, 24), 1)
        self.assertEqual(looks.hold_frames(24, 60), 1)

    def test_presets_are_consistent(self):
        self.assertEqual(set(looks.STYLES), set(looks.PRESET_CONTROLS))
        for style in looks.STYLES.values():
            self.assertLessEqual(style.max_len, 32)
            self.assertIn(style.underpaint, {"blur", "average"})


if __name__ == "__main__":
    unittest.main()
