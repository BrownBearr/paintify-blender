"""Shared settings compatibility and non-destructive brush selection."""

from dataclasses import replace
from pathlib import Path
import math
import sys
import types
import unittest

ADDON = Path(__file__).resolve().parents[1] / "blender_addon/paintify_gpu"
package = types.ModuleType("paintify_gpu")
package.__path__ = [str(ADDON)]
sys.modules.setdefault("paintify_gpu", package)
from paintify_gpu import brushkit
from paintify_gpu.looks import Look


class BrushkitTests(unittest.TestCase):
    def test_every_family_is_a_material_not_a_full_look(self):
        self.assertEqual(len(brushkit.BRUSHES), 24)
        for key in brushkit.BRUSHES:
            block = brushkit.select_brush(key)
            self.assertEqual(len(block), 260)
            self.assertEqual(block[2], 0, key)
            for name in ("fieldMode", "saturation", "groundMode", "contour", "rain"):
                index = brushkit.STYLE_INDEX[name]
                self.assertEqual(block[index], brushkit.DEFAULT_BLOCK[index], key)

    def test_brush_selection_keeps_edited_colour_and_finish(self):
        edited = list(brushkit.select_brush("cezanne"))
        for name, value in (("saturation", 1.7), ("fieldMode", 3), ("finish", 1),
                            ("vignette", .4), ("groundMode", 1)):
            edited[brushkit.STYLE_INDEX[name]] = value
        for key in ("monet", "none", "knife"):
            result = brushkit.select_brush(key, edited)
            for name in ("saturation", "fieldMode", "finish", "vignette", "groundMode"):
                index = brushkit.STYLE_INDEX[name]
                self.assertEqual(result[index], edited[index])

    def test_shared_look_roundtrip_including_palette_and_layer_overrides(self):
        block = list(brushkit.select_brush("vangogh"))
        block[52] = 2
        block[132:140] = (.2, .4, .8, 1, .9, .5, .1, 1)
        block[brushkit.STYLE_INDEX["finish"]] = 1
        look = Look(preset="balanced", brush_family="vangogh", style_block=tuple(block),
                    radii=(12, 6, 3), max_length=24, min_length=3, grid_factor=1.2,
                    stroke_opacity=.7, jitter_hue=.03, jitter_sat=.04, jitter_val=.05,
                    flow_levels=3, etf=2, fresh_paint=.6,
                    layer_specs=((8, 2, 30, math.nan, .8, math.nan),))
        loaded = brushkit.loads(brushkit.dumps(look))
        self.assertEqual(loaded.radii, look.radii)
        self.assertEqual(loaded.brush_family, look.brush_family)
        self.assertEqual(loaded.max_length, 24)
        self.assertEqual(loaded.flow_levels, 3)
        self.assertAlmostEqual(loaded.fresh_paint, .6)
        self.assertTrue(math.isnan(loaded.layer_specs[0][3]))
        for before, after in zip(look.style_block, loaded.style_block):
            self.assertAlmostEqual(before, after, places=6)

    def test_classic_save_resolves_legacy_defaults(self):
        look = Look(preset="pointillist")
        loaded = brushkit.loads(brushkit.dumps(look))
        self.assertEqual(loaded.style, look.style)

    def test_malformed_files_do_not_produce_a_look(self):
        for text in ("version 2", "radii nan", "radii 0", "style unknown",
                     "threshold inf", "threshold", "style-block 1 2", "layer 8 1 2 3 4 5 6"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                brushkit.loads(text)

    def test_radius_sets_do_not_change_stroke_or_material_settings(self):
        look = Look(preset="balanced", brush_family="cezanne", max_length=27, curvature=.2)
        for key, radii in brushkit.RADIUS_SETS.items():
            changed = replace(look, preset=key)
            self.assertEqual(changed.style.radii, radii)
            self.assertEqual(changed.style.max_len, 27)
            self.assertEqual(changed.curvature, .2)
            self.assertEqual(changed.brush_family, "cezanne")


if __name__ == "__main__":
    unittest.main()
