"""Scene settings shared by the viewport overlay and the render operators."""

import json
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, StringProperty, CollectionProperty)

from .looks import PRESET_CONTROLS, PRESETS, Look
from .brushkit import (BRUSHES, BRUSH_FIELDS, DEFAULT_BLOCK, RADIUS_SETS,
                       STYLE_FIELDS, STYLE_INDEX, select_brush)
from .controls import ENUMS, GROUPS


def _preset_changed(self, context):
    self.threshold, self.curvature, self.brush_texture = PRESET_CONTROLS[self.preset]


def _look_changed(self, context):
    self.bk_enabled = True


def _brush_changed(self, context):
    block = select_brush(self.brush_family, block_from_settings(self))
    for name in BRUSH_FIELDS:
        if name in ENUMS:
            setattr(self, "bk_" + name, str(int(block[STYLE_INDEX[name]])))
        else:
            setattr(self, "bk_" + name, block[STYLE_INDEX[name]])
    self.bk_finish = "0.5" if block[76] == 0.5 else str(int(block[76]))
    self.bk_enabled = block[0] > .5


def _radius_changed(self, context):
    if self.radius_set != "custom":
        self.radii_text = ', '.join(str(v) for v in RADIUS_SETS[self.radius_set])
        self.layer_specs = "[]"


class PAINTIFY_Pigment(bpy.types.PropertyGroup):
    color: FloatVectorProperty(name="Pigment", subtype="COLOR", size=3, min=0, max=1,
                               default=(.5, .5, .5))


class PAINTIFY_LiveSettings(bpy.types.PropertyGroup):
    data_version: IntProperty(default=0, options={"HIDDEN"})
    inspector_tab: EnumProperty(name="Inspector", items=[("LOOK", "Look", ""),
                               ("RENDER", "Render", "")], default="LOOK")
    brush_family: EnumProperty(name="Brush texture", items=[(key, item["name"], item["era"])
                              for key, item in BRUSHES.items()], default="none", update=_brush_changed)
    radius_set: EnumProperty(name="Radius set", items=[(key, key.replace('_', ' ').title(), "")
                             for key in RADIUS_SETS] + [("custom", "Custom", "")],
                             default="balanced", update=_radius_changed)
    radii_text: StringProperty(name="Radii", default="8, 4, 2")
    layer_specs: StringProperty(default="[]", options={"HIDDEN"})
    style_tail: StringProperty(default="", options={"HIDDEN"})
    pigments: CollectionProperty(type=PAINTIFY_Pigment)
    bk_enabled: BoolProperty(name="Material and effects", default=False)
    bk_finish: EnumProperty(name="Finish", items=[("0", "Off", ""),
                            ("0.5", "Brush relief", ""), ("1", "Full finish", "")],
                            default="0", update=_look_changed)
    ground_color: FloatVectorProperty(name="Ground colour", size=3, subtype="COLOR", min=0, max=1,
                                      default=(.93, .89, .8), update=_look_changed)
    contour_color: FloatVectorProperty(name="Contour colour", size=3, subtype="COLOR", min=0, max=1,
                                       default=(.23, .28, .5), update=_look_changed)
    varnish_color: FloatVectorProperty(name="Varnish tint", size=3, subtype="COLOR", min=0, max=1,
                                       default=(1, .9, .7), update=_look_changed)
    preset: EnumProperty(name="Style", items=[(p, p.title(), "") for p in PRESETS],
                         default="impressionist", update=_preset_changed)
    brush_size: FloatProperty(
        name="Brush size", default=1.0, min=0.25, max=4.0,
        description="Stroke size relative to the frame. The same value gives the same "
                    "look at any viewport or render resolution",
    )
    threshold: FloatProperty(name="Threshold", default=50, min=0, max=255)
    curvature: FloatProperty(name="Curvature", default=1, min=0, max=1)
    brush_texture: FloatProperty(name="Brush texture", default=0.45, min=0, max=1)
    impasto: FloatProperty(name="Impasto", default=0, min=0, max=1)
    impasto_light: FloatProperty(name="Impasto light", default=0, min=0, max=1)
    relax: IntProperty(name="Relaxation", default=0, min=0, max=12)
    temporal_diff: FloatProperty(
        name="Stroke stability", default=12, min=0, max=255,
        description="Source change (0-255) below which a region keeps the previous "
                    "frame's strokes. 0 repaints every frame from scratch",
    )
    opacity: FloatProperty(name="Overlay opacity", default=1, min=0, max=1)
    fps: IntProperty(
        name="Paint FPS", default=12, min=1, max=60,
        description="Painted frames per second in the viewport. With Stop-motion render, "
                    "also the cadence of rendered animation",
    )
    resolution: EnumProperty(
        name="Resolution", items=[("25", "25%", ""), ("50", "50%", ""),
                                  ("75", "75%", ""), ("100", "100%", "")],
        default="50",
        description="Viewport paint resolution. Renders always paint at full render size",
    )
    hold_frames: BoolProperty(
        name="Stop-motion render", default=True,
        description="Hold each painted frame for scene FPS / Paint FPS frames, as the "
                    "viewport does during playback. Off paints every frame",
    )

    max_length: FloatProperty(name="Maximum length", default=16, min=1, max=32, precision=0)
    min_length: FloatProperty(name="Minimum length", default=4, min=1, max=32, precision=0)
    grid_factor: FloatProperty(name="Grid spacing", default=1, min=.25, max=4)
    stroke_opacity: FloatProperty(name="Paint opacity", default=.9, min=0, max=1)
    underpaint: EnumProperty(name="Underpaint", items=[("blur", "Blur", ""),
                             ("average", "Average", ""), ("none", "White", "")], default="blur")
    jitter_hue: FloatProperty(name="Hue jitter", default=.05, min=0, max=1)
    jitter_sat: FloatProperty(name="Saturation jitter", default=.1, min=0, max=1)
    jitter_val: FloatProperty(name="Value jitter", default=.1, min=0, max=1)
    size_jitter: FloatProperty(name="Size jitter", default=0, min=0, max=1)
    angle_jitter: FloatProperty(name="Angle jitter", default=0, min=0, max=180)
    opacity_jitter: FloatProperty(name="Opacity jitter", default=0, min=0, max=1)
    texture_taper: FloatProperty(name="Tile taper", default=.4, min=0, max=1)
    dry_brush: FloatProperty(name="Dry brush", default=0, min=0, max=1)
    light_angle: FloatProperty(name="Light angle", default=45, min=0, max=360)
    jitter_per_frame: BoolProperty(name="Animated jitter", default=False)
    tensor_sigma: FloatProperty(name="Tensor smoothing", default=0, min=0, max=10)
    etf: IntProperty(name="ETF passes", default=0, min=0, max=8)
    etf_radius: FloatProperty(name="ETF radius", default=5, min=1, max=10)
    flow_levels: IntProperty(name="Motion levels", default=0, min=0, max=5)
    flow_iterations: IntProperty(name="Motion refinements", default=3, min=1, max=8)
    fresh_paint: FloatProperty(name="Fresh paint", default=0, min=0, max=1)
    bristle_density: FloatProperty(name="Tile bristles", default=10, min=1, max=32)
    passes: IntProperty(name="Painting passes", default=8, min=1, max=32)
    relax_area: FloatProperty(name="Paint economy", default=.06, min=0, max=1)
    relax_move: FloatProperty(name="Relaxation movement", default=.8, min=0, max=2)
    relax_candidates: IntProperty(name="Relaxation candidates", default=6, min=1, max=12)
    relax_remove: FloatProperty(name="Stroke removal", default=0, min=0, max=2)
    relax_subpasses: IntProperty(name="Relaxation subpasses", default=1, min=1, max=8)


for group in GROUPS.values():
    for name, label, low, high in group:
        PAINTIFY_LiveSettings.__annotations__["bk_" + name] = FloatProperty(
            name=label, default=DEFAULT_BLOCK[STYLE_INDEX[name]], min=low, max=high,
            update=_look_changed)
for name, (label, values) in ENUMS.items():
    PAINTIFY_LiveSettings.__annotations__["bk_" + name] = EnumProperty(
        name=label, items=[(str(i), value, "") for i, value in enumerate(values)],
        default=str(int(DEFAULT_BLOCK[STYLE_INDEX[name]])), update=_look_changed)
PAINTIFY_LiveSettings.__annotations__["bk_strokesOff"] = BoolProperty(
    name="Flat fill only", default=False, update=_look_changed)
PAINTIFY_LiveSettings.__annotations__["bk_temporalRefresh"] = FloatProperty(
    name="Paint renewal", default=0, min=0, max=1, update=_look_changed)
PAINTIFY_LiveSettings.__annotations__["bk_autoVortex"] = BoolProperty(
    name="Follow brightest area", default=False, update=_look_changed)


def block_from_settings(settings):
    values = list(DEFAULT_BLOCK)
    if settings.style_tail:
        values = list(json.loads(settings.style_tail))
    for name in STYLE_FIELDS:
        prop = "bk_" + name
        if hasattr(settings, prop):
            values[STYLE_INDEX[name]] = float(getattr(settings, prop))
    values[0] = float(settings.bk_enabled)
    values[1] = float(settings.brush_family != "none")
    values[STYLE_INDEX["seed"]] = BRUSHES[settings.brush_family]["values"][121]
    for name, color in (("groundR", settings.ground_color), ("contourR", settings.contour_color),
                        ("varnishR", settings.varnish_color)):
        start = STYLE_INDEX[name]
        values[start:start+3] = color
    values[52] = float(len(settings.pigments))
    for i, pigment in enumerate(settings.pigments):
        values[132+i*4:135+i*4] = pigment.color
    return tuple(values)


def migrate_settings(settings):
    if settings.data_version >= 1:
        return
    if settings.is_property_set("preset"):
        from .looks import STYLES
        style = STYLES[settings.preset]
        settings.radius_set = "custom"
        settings.radii_text = ', '.join(str(r) for r in style.radii)
        settings.max_length, settings.min_length = int(style.max_len), int(style.min_len)
        settings.grid_factor, settings.stroke_opacity = style.grid_factor, style.opacity
        settings.underpaint = style.underpaint
        settings.jitter_hue, settings.jitter_sat, settings.jitter_val = style.jitter
    settings.data_version = 1


def look_from_settings(settings):
    migrate_settings(settings)
    from .brushkit import loads, CORE_KEYS
    radii = loads("radii " + settings.radii_text).radii
    core = {name: getattr(settings, name) for name in CORE_KEYS.values()}
    core["jitter_per_frame"] = float(settings.jitter_per_frame)
    return Look(
        preset="balanced", radii=radii,
        brush_family=settings.brush_family, style_block=block_from_settings(settings),
        layer_specs=tuple(tuple(row) for row in json.loads(settings.layer_specs)),
        brush_size=settings.brush_size,
        underpaint=settings.underpaint,
        **core,
    )


def apply_look(settings, look):
    from .brushkit import CORE_KEYS
    settings.brush_family = look.brush_family
    settings.radius_set = "custom"
    settings.radii_text = ', '.join(str(r) for r in look.style.radii)
    settings.underpaint = look.style.underpaint
    for name in CORE_KEYS.values():
        value = getattr(look, name)
        if value is not None:
            if name == "jitter_per_frame":
                value = bool(value)
            setattr(settings, name, value)
    block = look.style_block or select_brush(look.brush_family)
    settings.style_tail = json.dumps(block)
    for name in STYLE_FIELDS:
        prop = "bk_" + name
        if hasattr(settings, prop):
            value = block[STYLE_INDEX[name]]
            if name in ENUMS:
                value = str(int(value))
            elif name == "finish":
                value = "0.5" if value == 0.5 else str(int(value))
            elif name in ("enabled", "strokesOff", "autoVortex"):
                value = bool(value)
            setattr(settings, prop, value)
    for prop, name in (("ground_color", "groundR"), ("contour_color", "contourR"),
                       ("varnish_color", "varnishR")):
        index = STYLE_INDEX[name]
        setattr(settings, prop, block[index:index+3])
    settings.pigments.clear()
    for i in range(min(16, int(block[52]))):
        settings.pigments.add().color = block[132+i*4:135+i*4]
    settings.layer_specs = json.dumps(look.layer_specs)
    settings.bk_enabled = block[0] > .5
    settings.data_version = 1
