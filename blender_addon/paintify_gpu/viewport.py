"""Live painted overlay for one 3D Viewport.

In camera view the overlay paints exactly the camera frame, drawn with the
camera's own projection at the render's aspect, so it previews what the
render operators produce. Elsewhere it paints the whole region.
"""

import time

import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader

from .looks import stroke_scale
from .painter import Painter
from .settings import look_from_settings

MAX_CAPTURE_PIXELS = 3840 * 2160


class _Viewport:
    painter = None
    handler = None
    area_pointer = None
    offscreen = None
    canvas = None
    last_capture = 0.0
    busy_capture = False
    failed = False
    error = ""
    result_time = 0.0
    actual_fps = 0.0


def running():
    return _Viewport.handler is not None


def status():
    return _Viewport.actual_fps, _Viewport.error


def render_size(scene):
    pct = scene.render.resolution_percentage / 100.0
    return (max(1, int(scene.render.resolution_x * pct)),
            max(1, int(scene.render.resolution_y * pct)))


def stop():
    if _Viewport.handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_Viewport.handler, "WINDOW")
        _Viewport.handler = None
    if _Viewport.offscreen is not None:
        _Viewport.offscreen.free()
        _Viewport.offscreen = None
    _Viewport.painter = None
    _Viewport.canvas = None
    _Viewport.area_pointer = None


def _camera_rect(scene, region, rv3d):
    """The camera frame's rectangle in region pixels, or None."""
    camera = scene.camera
    if camera is None or rv3d.view_perspective != "CAMERA":
        return None
    corners = [view3d_utils.location_3d_to_region_2d(region, rv3d, camera.matrix_world @ co)
               for co in camera.data.view_frame(scene=scene)]
    if any(c is None for c in corners):
        return None
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return x0, y0, x1, y1


def _capture_plan(context, settings, rect):
    """(width, height, view matrix, projection matrix) for the offscreen."""
    region = context.region
    scene = context.scene
    pct = int(settings.resolution) / 100.0
    if rect is not None:
        render_w, render_h = render_size(scene)
        # Keep the render's aspect exactly and never exceed its size.
        width = max(1, min(render_w, round((rect[2] - rect[0]) * pct)))
        height = max(1, round(width * render_h / render_w))
        camera = scene.camera
        projection = camera.calc_matrix_camera(
            context.evaluated_depsgraph_get(), x=render_w, y=render_h,
            scale_x=scene.render.pixel_aspect_x, scale_y=scene.render.pixel_aspect_y)
        view = camera.matrix_world.inverted()
    else:
        rv3d = context.space_data.region_3d
        width = max(1, int(region.width * pct))
        height = max(1, int(region.height * pct))
        view, projection = rv3d.view_matrix, rv3d.window_matrix
    if width * height > MAX_CAPTURE_PIXELS:
        shrink = (MAX_CAPTURE_PIXELS / (width * height)) ** 0.5
        width, height = max(1, int(width * shrink)), max(1, int(height * shrink))
    return width, height, view, projection


def _paint(context, settings, rect):
    width, height, view, projection = _capture_plan(context, settings, rect)
    offscreen = _Viewport.offscreen
    if offscreen is None or (offscreen.width, offscreen.height) != (width, height):
        if offscreen is not None:
            offscreen.free()
        offscreen = _Viewport.offscreen = gpu.types.GPUOffScreen(width, height)
    offscreen.draw_view3d(context.scene, context.view_layer, context.space_data, context.region,
                          view, projection, do_color_management=True)
    look = look_from_settings(settings)
    _Viewport.canvas = _Viewport.painter.paint(
        offscreen.texture_color, width, height, look,
        scale=stroke_scale(width, height, look.brush_size), temporal=True,
        frame=context.scene.frame_current)

    now = time.monotonic()
    if _Viewport.result_time:
        instant = 1.0 / max(now - _Viewport.result_time, 0.001)
        _Viewport.actual_fps = (0.75 * _Viewport.actual_fps + 0.25 * instant
                                if _Viewport.actual_fps else instant)
    _Viewport.result_time = now


def _draw_overlay():
    context = bpy.context
    area = context.area
    region = context.region
    if (not area or area.as_pointer() != _Viewport.area_pointer or region is None or
            region.type != "WINDOW" or _Viewport.busy_capture):
        return
    settings = context.scene.paintify_live
    rv3d = context.space_data.region_3d
    rect = _camera_rect(context.scene, region, rv3d)

    now = time.monotonic()
    if not _Viewport.failed and now - _Viewport.last_capture >= 1.0 / settings.fps:
        _Viewport.last_capture = now
        # draw_view3d runs the viewport's draw handlers again; skip that nesting.
        _Viewport.busy_capture = True
        try:
            _paint(context, settings, rect)
            _Viewport.error = ""
        except Exception as exc:
            # Stop retrying a broken pipeline every redraw; Stop/Start retries.
            _Viewport.failed = True
            _Viewport.error = f"Paint failed: {exc}"
            print("Paintify:", _Viewport.error)
        finally:
            _Viewport.busy_capture = False

    if _Viewport.canvas is None or settings.opacity <= 0:
        return
    x0, y0, x1, y1 = rect if rect is not None else (0, 0, region.width, region.height)
    if hasattr(_Viewport.canvas, "filter_mode"):  # Blender 4.3+
        _Viewport.canvas.filter_mode(True)
    shader = gpu.shader.from_builtin("IMAGE_COLOR")
    batch = batch_for_shader(shader, "TRI_FAN", {
        "pos": ((x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)),
        "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
    })
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_sampler("image", _Viewport.canvas)
    shader.uniform_float("color", (1, 1, 1, settings.opacity))
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def _tick():
    if _Viewport.handler is None:
        return None
    scene = bpy.context.scene
    fps = scene.paintify_live.fps if scene is not None else 12
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.as_pointer() == _Viewport.area_pointer:
                area.tag_redraw()
                return min(0.05, 0.5 / fps)
    stop()
    return None


class PAINTIFY_OT_toggle(bpy.types.Operator):
    bl_idname = "paintify.toggle_live"
    bl_label = "Toggle Paintify Live"
    bl_description = "Start or stop painting the active 3D Viewport"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        if running():
            stop()
            return {"FINISHED"}
        _Viewport.painter = Painter()
        _Viewport.area_pointer = context.area.as_pointer()
        _Viewport.error = ""
        _Viewport.failed = False
        _Viewport.last_capture = 0.0
        _Viewport.result_time = 0.0
        _Viewport.actual_fps = 0.0
        _Viewport.handler = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (), "WINDOW", "POST_PIXEL")
        bpy.app.timers.register(_tick, first_interval=0.05)
        context.area.tag_redraw()
        return {"FINISHED"}
