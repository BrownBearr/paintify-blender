"""Live Paintify GPU overlay for Blender's 3D Viewport."""

bl_info = {
    "name": "Paintify Live",
    "author": "BrownBearr",
    "version": (0, 2, 1),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Paintify",
    "description": "Live painterly overlay of the current 3D Viewport",
    "category": "3D View",
}

import time
from pathlib import Path

import bpy
import gpu
import numpy as np
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from gpu_extras.batch import batch_for_shader

from .stream_bridge import LiveBridge, Look, PRESETS, flip_rows


def _preset_changed(self, context):
    defaults = {
        "impressionist": (50, 1.0, 0.45),
        "expressionist": (40, 1.0, 0.60),
        "pointillist": (30, 0.0, 0.0),
        "wash": (80, 0.7, 0.0),
        "detail": (20, 1.0, 0.50),
    }
    self.threshold, self.curvature, self.brush_texture = defaults[self.preset]


class PAINTIFY_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    renderer_path: StringProperty(
        name="Live GPU renderer", subtype="FILE_PATH",
        description="Path to this repository's build/paintify-stream.exe",
        default=str(Path.home() / "paintify-blender" / "build" / "paintify-stream.exe"),
    )

    def draw(self, context):
        self.layout.prop(self, "renderer_path")


class PAINTIFY_LiveSettings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Style", items=[(p, p.title(), "") for p in PRESETS],
                         default="impressionist", update=_preset_changed)
    threshold: FloatProperty(name="Threshold", default=50, min=0, max=255)
    curvature: FloatProperty(name="Curvature", default=1, min=0, max=1)
    brush_texture: FloatProperty(name="Brush texture", default=0.45, min=0, max=1)
    impasto: FloatProperty(name="Impasto", default=0, min=0, max=1)
    impasto_light: FloatProperty(name="Impasto light", default=0, min=0, max=1)
    relax: IntProperty(name="Relaxation", default=0, min=0, max=12)
    temporal_diff: FloatProperty(name="Stroke stability", default=12, min=0, max=255)
    opacity: FloatProperty(name="Overlay opacity", default=1, min=0, max=1)
    fps: IntProperty(name="Paint FPS", default=12, min=1, max=60)
    resolution: EnumProperty(
        name="Resolution", items=[("25", "25%", ""), ("50", "50%", ""),
                                  ("75", "75%", ""), ("100", "100%", "")],
        default="50",
    )


class _Viewport:
    bridge = None
    handler = None
    area_pointer = None
    offscreen = None
    texture = None
    last_capture = 0.0
    sequence = 0
    busy_capture = False
    error = ""
    result_time = 0.0
    actual_fps = 0.0


def _stop():
    if _Viewport.handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_Viewport.handler, "WINDOW")
        _Viewport.handler = None
    if _Viewport.bridge is not None:
        _Viewport.bridge.close()
        _Viewport.bridge = None
    if _Viewport.offscreen is not None:
        _Viewport.offscreen.free()
        _Viewport.offscreen = None
    _Viewport.texture = None
    _Viewport.area_pointer = None


def _consume_result():
    frame = _Viewport.bridge.take_latest() if _Viewport.bridge else None
    if frame is None:
        return
    width, height, _sequence, pixels = frame
    now = time.monotonic()
    if _Viewport.result_time:
        instant = 1.0 / max(now - _Viewport.result_time, 0.001)
        _Viewport.actual_fps = (0.75 * _Viewport.actual_fps + 0.25 * instant
                                if _Viewport.actual_fps else instant)
    _Viewport.result_time = now
    # Pipeline returns top-first; GPUTexture data begins with the bottom row.
    bottom_up = flip_rows(pixels, width, height)
    # Blender 5.2's GPUTexture constructor accepts FLOAT data only, even for
    # an RGBA8 texture. Vectorize the conversion to keep frame uploads usable.
    normalized = np.frombuffer(bottom_up, dtype=np.uint8).astype(np.float32) / 255.0
    data = gpu.types.Buffer("FLOAT", (len(bottom_up),), normalized)
    _Viewport.texture = gpu.types.GPUTexture((width, height), format="RGBA8", data=data)


def _draw_overlay():
    context = bpy.context
    area = context.area
    region = context.region
    if (not area or area.type != "VIEW_3D" or
            area.as_pointer() != _Viewport.area_pointer or region.type != "WINDOW" or
            _Viewport.busy_capture):
        return
    settings = context.scene.paintify_live
    try:
        _consume_result()
    except Exception as exc:
        _Viewport.error = f"Overlay upload failed: {exc}"
        return
    now = time.monotonic()
    if (_Viewport.bridge and not _Viewport.bridge.error and
            now - _Viewport.last_capture >= 1.0 / settings.fps and
            not _Viewport.bridge.inflight):
        width = max(1, int(region.width * int(settings.resolution) / 100))
        height = max(1, int(region.height * int(settings.resolution) / 100))
        if width * height <= 3840 * 2160:
            _Viewport.last_capture = now
            _Viewport.busy_capture = True
            try:
                if (_Viewport.offscreen is None or
                        (_Viewport.offscreen.width, _Viewport.offscreen.height) != (width, height)):
                    if _Viewport.offscreen is not None:
                        _Viewport.offscreen.free()
                    _Viewport.offscreen = gpu.types.GPUOffScreen(width, height)
                rv3d = context.space_data.region_3d
                _Viewport.offscreen.draw_view3d(
                    context.scene, context.view_layer, context.space_data, region,
                    rv3d.view_matrix, rv3d.window_matrix, do_color_management=True,
                )
                with _Viewport.offscreen.bind():
                    pixels = gpu.state.active_framebuffer_get().read_color(
                        0, 0, width, height, 4, 0, "UBYTE")
                pixels.dimensions = width * height * 4
                top_down = flip_rows(bytes(pixels.to_list()), width, height)
                look = Look(
                    threshold=settings.threshold, curvature=settings.curvature,
                    brush_texture=settings.brush_texture, impasto=settings.impasto,
                    impasto_light=settings.impasto_light,
                    temporal_diff=settings.temporal_diff, relax=settings.relax,
                    preset=PRESETS.index(settings.preset),
                )
                _Viewport.sequence += 1
                _Viewport.bridge.submit(width, height, _Viewport.sequence, top_down, look)
                _Viewport.error = ""
            except Exception as exc:
                _Viewport.error = str(exc)
            finally:
                _Viewport.busy_capture = False

    if _Viewport.texture is not None and settings.opacity > 0:
        shader = gpu.shader.from_builtin("IMAGE_COLOR")
        batch = batch_for_shader(shader, "TRI_FAN", {
            "pos": ((0, 0, 0), (region.width, 0, 0),
                    (region.width, region.height, 0), (0, region.height, 0)),
            "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
        })
        gpu.state.blend_set("ALPHA")
        shader.bind()
        shader.uniform_sampler("image", _Viewport.texture)
        shader.uniform_float("color", (1, 1, 1, settings.opacity))
        batch.draw(shader)
        gpu.state.blend_set("NONE")


def _tick():
    if _Viewport.bridge is None:
        return None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.as_pointer() == _Viewport.area_pointer:
                area.tag_redraw()
                return 0.05
    _stop()
    return None


class PAINTIFY_OT_toggle(bpy.types.Operator):
    bl_idname = "paintify.toggle_live"
    bl_label = "Toggle Paintify Live"
    bl_description = "Start or stop painting the active 3D Viewport"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        if _Viewport.bridge is not None:
            _stop()
            return {"FINISHED"}
        preferences = context.preferences.addons[__package__].preferences
        try:
            _Viewport.bridge = LiveBridge(bpy.path.abspath(preferences.renderer_path))
        except OSError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        _Viewport.area_pointer = context.area.as_pointer()
        _Viewport.error = ""
        _Viewport.last_capture = 0.0
        _Viewport.result_time = 0.0
        _Viewport.actual_fps = 0.0
        _Viewport.handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (), "WINDOW", "POST_PIXEL")
        bpy.app.timers.register(_tick, first_interval=0.05)
        context.area.tag_redraw()
        return {"FINISHED"}


class PAINTIFY_PT_live(bpy.types.Panel):
    bl_label = "Paintify Live"
    bl_idname = "PAINTIFY_PT_live"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paintify"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.paintify_live
        running = _Viewport.bridge is not None
        layout.operator("paintify.toggle_live", text="Stop Live Paint" if running else "Start Live Paint",
                        icon="PAUSE" if running else "PLAY")
        layout.prop(settings, "preset")
        layout.prop(settings, "threshold")
        layout.prop(settings, "curvature")
        layout.prop(settings, "brush_texture")
        layout.prop(settings, "impasto")
        layout.prop(settings, "impasto_light")
        layout.prop(settings, "relax")
        layout.prop(settings, "temporal_diff")
        layout.prop(settings, "opacity")
        layout.prop(settings, "fps")
        layout.prop(settings, "resolution")
        if running and _Viewport.actual_fps:
            layout.label(text=f"Measured paint: {_Viewport.actual_fps:.1f} FPS")
        if running and _Viewport.bridge.error:
            layout.label(text=_Viewport.bridge.error[:55], icon="ERROR")
        if _Viewport.error:
            layout.label(text=_Viewport.error[:55], icon="ERROR")


CLASSES = (PAINTIFY_Preferences, PAINTIFY_LiveSettings,
           PAINTIFY_OT_toggle, PAINTIFY_PT_live)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.paintify_live = PointerProperty(type=PAINTIFY_LiveSettings)


def unregister():
    _stop()
    del bpy.types.Scene.paintify_live
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
