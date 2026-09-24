"""Run with: blender --background --factory-startup --python tests/blender_smoke.py"""

from pathlib import Path
import sys
import time

import bpy
import gpu

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "blender_addon"))
gpu.init()  # Blender 5.2 background sessions need an explicit GPU context.
bpy.ops.preferences.addon_enable(module="paintify_gpu")
import paintify_gpu
from paintify_gpu import _Viewport, _draw_overlay
assert Path(paintify_gpu.__file__).resolve() == (root / "blender_addon" / "paintify_gpu" / "__init__.py").resolve()
bpy.context.preferences.addons["paintify_gpu"].preferences.renderer_path = str(root / "build" / "paintify-stream.exe")
try:
    area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
        assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
        _draw_overlay()
        deadline = time.monotonic() + 10
        while _Viewport.bridge.inflight and time.monotonic() < deadline:
            time.sleep(0.05)
        _draw_overlay()
        assert not _Viewport.error, _Viewport.error
        assert not _Viewport.bridge.error, _Viewport.bridge.error
        assert _Viewport.texture is not None, "No painted overlay texture"
        assert bpy.ops.paintify.toggle_live() == {"FINISHED"}
        assert _Viewport.bridge is None
        print("PAINTIFY_BLENDER_SMOKE_OK")
finally:
    if _Viewport.bridge is not None:
        paintify_gpu._stop()
    bpy.ops.preferences.addon_disable(module="paintify_gpu")
