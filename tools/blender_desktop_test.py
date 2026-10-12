"""Run smoke checks after Blender creates a desktop Metal context, then quit."""

from pathlib import Path
import runpy
import traceback
import bpy

ROOT = Path(__file__).resolve().parents[1]


def run():
    try:
        runpy.run_path(str(ROOT / "tests/blender_smoke.py"), run_name="__main__")
    except Exception:
        traceback.print_exc()
        print("PAINTIFY_BLENDER_SMOKE_FAILED", flush=True)
    finally:
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(run, first_interval=1.0)
