"""Run with: blender --background --factory-startup --python tests/blender_smoke.py

Also runs under the `bpy` module (pip install bpy): python tests/blender_smoke.py
Linux needs a display or EGL for Blender's GPU module; xvfb-run works.
"""

from pathlib import Path
from dataclasses import replace
import os
import sys
import tempfile
from types import SimpleNamespace

import bpy
import gpu
import numpy as np

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "blender_addon"))
if hasattr(gpu, "init"):
    gpu.init()  # Blender 5.x background sessions need an explicit GPU context.
bpy.ops.preferences.addon_enable(module="paintify_gpu")
import paintify_gpu
from paintify_gpu import painter, viewport
from paintify_gpu import brushkit
from paintify_gpu.settings import apply_look, look_from_settings
from paintify_gpu.looks import Look, stroke_scale

assert Path(paintify_gpu.__file__).resolve() == (root / "blender_addon" / "paintify_gpu" / "__init__.py").resolve()
print("Blender", bpy.app.version_string, "GPU backend", gpu.platform.backend_type_get())
bpy.ops.preferences.addon_disable(module="paintify_gpu")
bpy.ops.preferences.addon_enable(module="paintify_gpu")
print("Add-on re-enable OK", flush=True)


def check_painter():
    w, h = 320, 180
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    src = np.zeros((h, w, 4), np.float32)
    src[..., 0], src[..., 1], src[..., 2], src[..., 3] = x / w, y / h, 0.4, 1.0
    src[(x - 160) ** 2 + (y - 90) ** 2 < 900, :3] = (0.9, 0.2, 0.1)
    texture = painter.texture_from_pixels(src.ravel(), w, h)
    uploaded = painter.read_texture_pixels(texture)
    assert np.abs(uploaded - src).max() < .001, "GPU upload/readback changed channel or pixel order"
    for look in (Look(), Look(preset="pointillist"), Look(relax=2, impasto=0.5, impasto_light=0.5)):
        p = painter.Painter()
        p.paint(texture, w, h, look, scale=stroke_scale(w, h))
        first = p.read_pixels()
        print("Paint difference", look.brush_family, float(np.abs(first[..., :3] - src[..., :3]).mean()),
              "range", float(first.min()), float(first.max()), flush=True)
        assert first.shape == (h, w, 4) and np.isfinite(first).all(), look
        assert 0.005 < np.abs(first[..., :3] - src[..., :3]).mean() < 0.2, look
        p.paint(texture, w, h, look, scale=stroke_scale(w, h))
        assert np.array_equal(first, p.read_pixels()), "an unchanged source must keep its strokes"
        assert p.render_count == 1, "a still should be painted once"
        again = painter.Painter()
        again.paint(texture, w, h, look, scale=stroke_scale(w, h))
        assert np.array_equal(first, again.read_pixels()), "painting must be deterministic"


def check_no_trails():
    """A square sliding over a textured ground must not leave red strokes in
    the area it has left, with stroke stability at its default."""
    w, h = 480, 270
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    ground = np.zeros((h, w, 4), np.float32)
    ground[..., 0] = 0.3 + 0.2 * np.sin(x / 23)
    ground[..., 1] = 0.5 + 0.2 * np.cos(y / 17)
    ground[..., 2], ground[..., 3] = 0.6, 1.0
    p = painter.Painter()
    look = Look()
    assert look.temporal_diff > 0, "the default should keep strokes stable"
    for step in range(8):
        frame = ground.copy()
        x0 = 60 + step * 30
        frame[90:180, x0:x0 + 70, :3] = (0.9, 0.15, 0.1)
        p.paint(painter.texture_from_pixels(frame.ravel(), w, h), w, h, look,
                scale=stroke_scale(w, h))
    left_behind = p.read_pixels()[80:190, 40:x0 - 10, :3]
    red = (left_behind[..., 0] > 0.6) & (left_behind[..., 1] < 0.35)
    assert red.mean() == 0.0, f"trail behind the moving square: {red.mean():.4f}"


def check_brushkit():
    w, h = 160, 96
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    src = np.stack((x/w, y/h, .3+.2*np.sin(x/8), np.ones_like(x)), axis=-1)
    texture = painter.texture_from_pixels(src.ravel(), w, h)
    for key in brushkit.BRUSHES:
        look = Look(preset="balanced", brush_family=key, temporal_diff=12)
        p = painter.Painter()
        p.paint(texture, w, h, look, scale=stroke_scale(w, h))
        first = p.read_pixels()
        assert first.shape == src.shape and np.isfinite(first).all(), key
        assert np.all(first[..., 3] == 1), key
        assert first[..., :3].std() > .03, key
        p.paint(texture, w, h, look, scale=stroke_scale(w, h))
        assert p.render_count == 1 and np.array_equal(first, p.read_pixels()), key
        print("Brushkit material OK", key, flush=True)

    block = list(brushkit.select_brush("cezanne"))
    for name, value in (("fieldMode", 3), ("minFieldMag", .05), ("saturation", 1.2),
                        ("groundMode", 1), ("finish", 1), ("contour", .6),
                        ("vignette", .2), ("licStrength", .2)):
        block[brushkit.STYLE_INDEX[name]] = value
    look = Look(preset="balanced", brush_family="cezanne", style_block=tuple(block),
                etf=1, tensor_sigma=1, flow_levels=2, fresh_paint=.5,
                layer_specs=((8, 2, 10, float('nan'), .8, float('nan')),))
    scene_settings = bpy.context.scene.paintify_live
    apply_look(scene_settings, brushkit.loads(brushkit.dumps(look)))
    restored = look_from_settings(scene_settings)
    assert restored.flow_levels == 2 and restored.etf == 1
    assert abs(restored.style_block[brushkit.STYLE_INDEX["saturation"]]-1.2) < 1e-6
    p = painter.Painter()
    p.paint(texture, w, h, restored, scale=stroke_scale(w, h))
    first = p.read_pixels()
    p.paint(texture, w, h, restored, scale=stroke_scale(w, h), frame=1)
    assert p.render_count == 1 and np.array_equal(first, p.read_pixels())
    moved = painter.texture_from_pixels(np.roll(src, 3, axis=1).ravel(), w, h)
    p.paint(moved, w, h, restored, scale=stroke_scale(w, h), frame=2)
    assert p.render_count == 2 and np.isfinite(p.read_pixels()).all()
    assert not np.array_equal(first, p.read_pixels()), "motion must repaint"
    print("Brushkit settings, ETF, tensor, motion and fresh paint OK", flush=True)

    flat = list(brushkit.select_brush("pop"))
    for name, value in (("groundMode", 2), ("strokesOff", 1), ("watercolor", 1),
                        ("halftone", .5), ("outline", .5)):
        flat[brushkit.STYLE_INDEX[name]] = value
    p = painter.Painter()
    p.paint(texture, w, h, replace(look, style_block=tuple(flat), relax=2), scale=stroke_scale(w, h))
    assert np.isfinite(p.read_pixels()).all() and p.read_pixels()[..., :3].std() > .02
    print("Brushkit flat ground, wash and overlays OK", flush=True)
    flat[0] = 0
    p = painter.Painter()
    p.paint(texture, w, h, replace(look, style_block=tuple(flat), etf=0, tensor_sigma=0,
                                  layer_specs=()), scale=stroke_scale(w,h))
    disabled = p.read_pixels()
    plain = painter.Painter()
    plain.paint(texture,w,h,Look(preset="balanced"),scale=stroke_scale(w,h))
    assert np.array_equal(disabled, plain.read_pixels()), "disabled material must use the classic path"

    scene_settings.data_version = 0
    scene_settings.preset = "pointillist"
    migrated = look_from_settings(scene_settings)
    # Panels and the overlay read settings while Blender draws, where writing
    # to a scene raises; reading must migrate in memory only.
    assert scene_settings.data_version == 0, "look_from_settings wrote to the scene"
    assert migrated.radii == (4, 2) and migrated.max_length == 3
    assert migrated.curvature == 0 and migrated.underpaint == "average"
    apply_look(scene_settings, restored)
    print("Material disable and legacy scene migration OK", flush=True)
    sky = np.empty_like(src)
    sky[:] = (.1, .3, .7, 1)
    sky_texture = painter.texture_from_pixels(sky.ravel(), w, h)
    sky_block = list(brushkit.select_brush("ukiyoe"))
    for name, value in (("groundMode", 2), ("strokesOff", 1), ("bokashi", .8)):
        sky_block[brushkit.STYLE_INDEX[name]] = value
    p = painter.Painter()
    p.paint(sky_texture, w, h, Look(preset="balanced", brush_family="ukiyoe",
            style_block=tuple(sky_block)), scale=stroke_scale(w,h))
    pixels = p.read_pixels()
    assert pixels[-10:, :, :3].mean() < pixels[:10, :, :3].mean() - .02, "bokashi belongs at the top"
    print("Shared look coordinate orientation OK", flush=True)


def check_viewport(area, region):
    scene = bpy.context.scene
    assert "paintify_gpu" in bpy.context.preferences.addons
    preferences = bpy.context.preferences.addons["paintify_gpu"].preferences
    assert preferences.bl_rna.identifier == "PAINTIFY_LIVE_preferences"
    assert not hasattr(bpy.types, "PAINTIFY_LIVE_PT_render_properties")
    assert bpy.types.PAINTIFY_LIVE_PT_playback.bl_space_type == "VIEW_3D"
    assert bpy.types.PAINTIFY_LIVE_PT_playback.bl_region_type == "UI"
    assert "HIDE_HEADER" in bpy.types.PAINTIFY_LIVE_PT_playback.bl_options
    class LayoutRecorder:
        def __init__(self):
            self.buttons = []

        def row(self, **kwargs):
            return self

        def operator(self, identifier, **kwargs):
            self.buttons.append((identifier, kwargs.get("text")))
            return SimpleNamespace()

        def prop(self, *args, **kwargs):
            pass

    for panel in (paintify_gpu.ui.PAINTIFY_LIVE_preferences,
                  paintify_gpu.ui.PAINTIFY_LIVE_PT_playback,
                  paintify_gpu.ui.PAINTIFY_PT_live):
        layout = LayoutRecorder()
        panel.draw(SimpleNamespace(layout=layout), bpy.context)
        assert ("paintify.toggle_live", "Start Live Paint") in layout.buttons
    other = next((a for a in bpy.context.screen.areas if a.type != "VIEW_3D"), None)
    if other is not None:
        with bpy.context.temp_override(area=other):
            assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
            assert viewport.running()
            assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
        assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
        try:
            layout = LayoutRecorder()
            paintify_gpu.ui.PAINTIFY_LIVE_PT_playback.draw(SimpleNamespace(layout=layout), bpy.context)
            assert ("paintify.toggle_live", "Stop Live Paint") in layout.buttons
            viewport._draw_overlay()
            assert not viewport._Viewport.error, viewport._Viewport.error
            assert viewport._Viewport.canvas is not None, "No painted overlay"
            # Camera view paints the camera frame at the render's aspect.
            area.spaces.active.region_3d.view_perspective = "CAMERA"
            viewport._Viewport.last_capture = 0.0
            viewport._draw_overlay()
            assert not viewport._Viewport.error, viewport._Viewport.error
            canvas = viewport._Viewport.canvas
            aspect = scene.render.resolution_x / scene.render.resolution_y
            assert abs(canvas.width / canvas.height - aspect) < 0.05, (canvas.width, canvas.height)
            # Once nothing has changed for the settle period, redraws stop painting.
            viewport._Viewport.last_change -= viewport.SETTLE_SECONDS + 1.0
            viewport._Viewport.last_capture = 0.0
            viewport._draw_overlay()
            assert viewport._Viewport.last_capture == 0.0, "an unchanged view repainted"
            assert viewport.idle()
        finally:
            assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
    assert not viewport.running()


def check_render(out_dir):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = 192, 108
    scene.render.resolution_percentage = 100
    scene.render.fps, scene.render.fps_base = 24, 1.0
    scene.paintify_live.fps = 12
    scene.frame_start, scene.frame_end = 1, 4
    cube = bpy.data.objects.get("Cube")
    if cube is not None:
        cube.rotation_euler = (0.0, 0.0, 0.0)
        cube.keyframe_insert("rotation_euler", frame=1)
        cube.rotation_euler = (0.0, 0.0, 1.2)
        cube.keyframe_insert("rotation_euler", frame=4)

    assert bpy.ops.paintify.render_image() == {"FINISHED"}
    image = bpy.data.images["Paintify Render"]
    assert tuple(image.size) == (192, 108), tuple(image.size)
    pixels = np.empty(192 * 108 * 4, np.float32)
    image.pixels.foreach_get(pixels)
    still = pixels.reshape(108, 192, 4)
    assert still[..., :3].std() > 0.01, "painted still is blank"

    # Image sequence, held on twos: 24 FPS scene painted at 12 FPS.
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "IMAGE"
    settings.file_format = "PNG"
    scene.render.filepath = os.path.join(out_dir, "seq_")
    assert bpy.ops.paintify.render_animation() == {"FINISHED"}
    frames = []
    for frame in range(1, 5):
        path = scene.render.frame_path(frame=frame)
        assert os.path.isfile(path), path
        loaded = bpy.data.images.load(path, check_existing=False)
        px = np.empty(192 * 108 * 4, np.float32)
        loaded.pixels.foreach_get(px)
        bpy.data.images.remove(loaded)
        frames.append(px)
    assert np.array_equal(frames[0], frames[1]) and np.array_equal(frames[2], frames[3])
    # Frame 1 of the sequence and the still paint the same render, so the
    # writer must not shift colour beyond 8-bit rounding.
    first = frames[0].reshape(108, 192, 4)[..., :3]
    assert np.abs(first - still[..., :3]).max() <= 1.5 / 255, np.abs(first - still[..., :3]).max()
    assert not np.array_equal(frames[1], frames[2]), "the cube turns, so the painting should change"
    assert "Paintify Output" not in bpy.data.scenes, "scratch scene left behind"
    assert scene.render.image_settings.file_format == "PNG"

    # Movie through Blender's encoder.
    if hasattr(settings, "media_type"):
        settings.media_type = "VIDEO"
    settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.filepath = os.path.join(out_dir, "movie_")
    assert bpy.ops.paintify.render_animation() == {"FINISHED"}
    movie = scene.render.frame_path(frame=1)
    assert os.path.isfile(movie) and os.path.getsize(movie) > 0, movie
    clip = bpy.data.images.load(movie, check_existing=False)
    px = np.empty(192 * 108 * 4, np.float32)
    clip.pixels.foreach_get(px)
    bpy.data.images.remove(clip)
    # H.264 subsamples chroma, so compare the mean colour only.
    shift = np.abs(px.reshape(108, 192, 4)[..., :3].mean((0, 1)) - first.mean((0, 1))).max()
    assert shift < 0.02, shift
    assert settings.file_format == "FFMPEG", "output settings must be restored"


try:
    check_painter()
    check_no_trails()
    check_brushkit()
    area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    check_viewport(area, region)
    with tempfile.TemporaryDirectory() as out_dir:
        check_render(out_dir)
    print("PAINTIFY_BLENDER_SMOKE_OK")
finally:
    viewport.stop()
    bpy.ops.preferences.addon_disable(module="paintify_gpu")
