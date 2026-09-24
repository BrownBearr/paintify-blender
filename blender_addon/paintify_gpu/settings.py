"""Scene settings shared by the viewport overlay and the render operators."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty

from .looks import PRESET_CONTROLS, PRESETS, Look


def _preset_changed(self, context):
    self.threshold, self.curvature, self.brush_texture = PRESET_CONTROLS[self.preset]


class PAINTIFY_LiveSettings(bpy.types.PropertyGroup):
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


def look_from_settings(settings):
    return Look(
        preset=settings.preset, threshold=settings.threshold,
        curvature=settings.curvature, brush_texture=settings.brush_texture,
        impasto=settings.impasto, impasto_light=settings.impasto_light,
        relax=settings.relax, temporal_diff=settings.temporal_diff,
        brush_size=settings.brush_size,
    )
