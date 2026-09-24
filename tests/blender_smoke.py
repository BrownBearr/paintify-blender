"""Run with: blender --background --factory-startup --python tests/blender_smoke.py

Also runs under the `bpy` module (pip install bpy): python tests/blender_smoke.py
Linux needs a display or EGL for Blender's GPU module; xvfb-run works.
"""

from pathlib import Path
import os
import sys
import tempfile

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
from paintify_gpu.looks import Look, stroke_scale

assert Path(paintify_gpu.__file__).resolve() == (root / "blender_addon" / "paintify_gpu" / "__init__.py").resolve()
print("Blender", bpy.app.version_string, "GPU backend", gpu.platform.backend_type_get())


def check_painter():
    w, h = 320, 180
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    src = np.zeros((h, w, 4), np.float32)
    src[..., 0], src[..., 1], src[..., 2], src[..., 3] = x / w, y / h, 0.4, 1.0
    src[(x - 160) ** 2 + (y - 90) ** 2 < 900, :3] = (0.9, 0.2, 0.1)
    texture = painter.texture_from_pixels(src.ravel(), w, h)
    for look in (Look(), Look(preset="pointillist"), Look(relax=2, impasto=0.5, impasto_light=0.5)):
        p = painter.Painter()
        p.paint(texture, w, h, look, scale=stroke_scale(w, h))
        first = p.read_pixels()
        assert first.shape == (h, w, 4) and np.isfinite(first).all(), look
        assert 0.005 < np.abs(first[..., :3] - src[..., :3]).mean() < 0.2, look
        p.paint(texture, w, h, look, scale=stroke_scale(w, h))
        assert np.array_equal(first, p.read_pixels()), "an unchanged source must keep its strokes"
        again = painter.Painter()
        again.paint(texture, w, h, look, scale=stroke_scale(w, h))
        assert np.array_equal(first, again.read_pixels()), "painting must be deterministic"


def check_viewport(area, region):
    scene = bpy.context.scene
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
        assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
        try:
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
    area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    check_viewport(area, region)
    with tempfile.TemporaryDirectory() as out_dir:
        check_render(out_dir)
    print("PAINTIFY_BLENDER_SMOKE_OK")
finally:
    viewport.stop()
    bpy.ops.preferences.addon_disable(module="paintify_gpu")
