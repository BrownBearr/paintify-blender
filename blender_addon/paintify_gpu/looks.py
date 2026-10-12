"""Style tables and the geometry that keeps a look resolution independent.

Pure Python so it can be tested without Blender.
"""

from dataclasses import dataclass, fields
import math
from .brushkit import RADIUS_SETS

# Brush radii are defined for an image whose geometric mean side is this many
# pixels (800x450). Everything else scales with sqrt(width * height), so a
# 50% viewport preview and a 4K render of the same camera frame get strokes of
# the same size relative to the frame.
REFERENCE_SIDE = 600.0

# Stroke-store sizing, shared with the shaders: slots per pass are bounded by
# this, and a layer never takes fewer than MIN_PASSES or more than MAX_PASSES
# passes. More passes give later strokes more earlier paint to stop against.
PASS_CAPACITY = 200_000
MIN_PASSES = 8
MAX_PASSES = 32


@dataclass(frozen=True)
class Style:
    radii: tuple
    max_len: float
    min_len: float
    grid_factor: float
    opacity: float
    jitter: tuple  # hue, saturation, value
    underpaint: str  # "blur" or "average"


# Same values as the web presets that paintify-GPU mirrors.
STYLES = {
    "impressionist": Style((8.0, 4.0, 2.0), 16, 4, 1.0, 0.90, (0.05, 0.10, 0.10), "blur"),
    "expressionist": Style((12.0, 6.0, 3.0), 28, 8, 0.9, 0.95, (0.15, 0.20, 0.15), "blur"),
    "pointillist": Style((4.0, 2.0), 3, 1, 0.75, 0.85, (0.10, 0.15, 0.10), "average"),
    "wash": Style((20.0, 10.0), 32, 10, 1.5, 0.40, (0.20, 0.30, 0.20), "blur"),
    "detail": Style((6.0, 3.0, 1.5), 10, 4, 1.0, 1.00, (0.0, 0.0, 0.0), "blur"),
}
PRESETS = tuple(STYLES)

# Threshold, curvature and brush texture each style starts from in the panel.
PRESET_CONTROLS = {
    "impressionist": (50.0, 1.0, 0.45),
    "expressionist": (40.0, 1.0, 0.60),
    "pointillist": (30.0, 0.0, 0.0),
    "wash": (80.0, 0.7, 0.0),
    "detail": (20.0, 1.0, 0.50),
}


@dataclass(frozen=True)
class Look:
    """Every setting that changes the painting. Frozen, so it can be compared
    to decide whether the previous frame's paint may carry forward."""

    preset: str = "impressionist"
    threshold: float = 50.0
    curvature: float = 1.0
    brush_texture: float = 0.45
    impasto: float = 0.0
    impasto_light: float = 0.0
    relax: int = 0
    temporal_diff: float = 12.0
    brush_size: float = 1.0
    brush_family: str = "none"
    style_block: tuple = ()
    radii: tuple = ()
    layer_specs: tuple = ()
    max_length: float = None
    min_length: float = None
    grid_factor: float = None
    stroke_opacity: float = None
    underpaint: str = ""
    jitter_hue: float = None
    jitter_sat: float = None
    jitter_val: float = None
    size_jitter: float = 0.0
    angle_jitter: float = 0.0
    opacity_jitter: float = 0.0
    texture_taper: float = 0.4
    dry_brush: float = 0.0
    light_angle: float = 45.0
    jitter_per_frame: float = 0.0
    tensor_sigma: float = 0.0
    etf: int = 0
    etf_radius: float = 5.0
    flow_levels: int = 0
    flow_iterations: int = 3
    fresh_paint: float = 0.0
    bristle_density: float = 10.0
    passes: int = 8
    relax_area: float = 0.06
    relax_move: float = 0.8
    relax_candidates: int = 6
    relax_remove: float = 0.0
    relax_subpasses: int = 1

    @property
    def cache_key(self):
        # NaN means "use the global value" in imported per-layer settings.
        # Distinct NaN objects must compare as the same setting across frames.
        layers = tuple(tuple(None if math.isnan(v) else v for v in layer)
                       for layer in self.layer_specs)
        return tuple(layers if f.name == "layer_specs" else getattr(self, f.name)
                     for f in fields(self))

    @property
    def style(self):
        legacy = STYLES.get(self.preset, STYLES["impressionist"])
        modern = self.preset in RADIUS_SETS
        def value(name, fallback):
            v = getattr(self, name)
            return fallback if v is None else v
        return Style(
            self.radii or RADIUS_SETS.get(self.preset, legacy.radii),
            value("max_length", 16 if modern else legacy.max_len),
            value("min_length", 4 if modern else legacy.min_len),
            value("grid_factor", 1 if modern else legacy.grid_factor),
            value("stroke_opacity", 0.9 if modern else legacy.opacity),
            (value("jitter_hue", 0.05 if modern else legacy.jitter[0]),
             value("jitter_sat", 0.10 if modern else legacy.jitter[1]),
             value("jitter_val", 0.10 if modern else legacy.jitter[2])),
            self.underpaint or ("blur" if modern else legacy.underpaint),
        )


def stroke_scale(width, height, brush_size=1.0):
    """Pixels per reference pixel for an image of this size."""
    return math.sqrt(max(1, width) * max(1, height)) / REFERENCE_SIDE * brush_size


def layer_radii(style, scale):
    """Coarse to fine. Radii are clamped to one pixel rather than dropped, so a
    small preview keeps the same layers as the full render."""
    return tuple(sorted((max(1.0, r * scale) for r in style.radii), reverse=True))


@dataclass(frozen=True)
class LayerPlan:
    radius: float
    grid: int
    cells_x: int
    cells_y: int
    passes: int
    slots: int  # strokes per pass: one per block of `passes` cells

    @property
    def cells(self):
        return self.cells_x * self.cells_y


def plan_layer(width, height, radius, grid_factor, passes=MIN_PASSES):
    # worker.js: grid = max(1, round(radius * gridFactor)).
    grid = max(1, int(math.floor(radius * grid_factor + 0.5)))
    cells_x = -(-width // grid)
    cells_y = -(-height // grid)
    cells = cells_x * cells_y
    passes = min(MAX_PASSES, max(1, passes, -(-cells // PASS_CAPACITY)))
    return LayerPlan(radius, grid, cells_x, cells_y, passes, -(-cells // passes))


def brush_rows(radius):
    """Tile rows in use for a radius (paintify-GPU brush_atlas.cpp rowsForRadius)."""
    return max(8, min(48, int(math.floor(2.0 * max(1.0, radius) + 0.5))))


def hold_frames(scene_fps, paint_fps):
    """Scene frames each painted frame is held for, the stop-motion cadence
    the viewport shows during playback."""
    if paint_fps <= 0 or scene_fps <= paint_fps:
        return 1
    return max(1, int(round(scene_fps / paint_fps)))


_ORDER_STEPS = (1543, 1549, 1553, 1559, 1567, 1571, 1579, 1583, 1597, 1601)


def draw_order_step(count):
    """A step coprime to `count`, so instance i -> (i * step) % count visits
    every slot once. Small enough that i * step fits in 32 bits."""
    for step in _ORDER_STEPS:
        if count % step:
            return step
    return 1
