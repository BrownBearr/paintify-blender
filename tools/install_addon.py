"""Install the packaged add-on in the running Blender version and enable it."""

from datetime import datetime
from pathlib import Path
import shutil
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parents[1]
preferences = Path(bpy.utils.user_resource("CONFIG")) / "userpref.blend"
if preferences.is_file():
    backup = preferences.with_name("userpref-before-paintify-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".blend")
    shutil.copy2(preferences, backup)
    print("Preferences backup:", backup)
bpy.ops.preferences.addon_install(filepath=str(ROOT / "dist/paintify_live_mac.zip"),
                                 overwrite=True, enable_on_install=False)
addon_utils.enable("paintify_gpu", default_set=True, persistent=True)
assert addon_utils.check("paintify_gpu") == (True, True)
assert hasattr(bpy.types.Scene, "paintify_live")
import paintify_gpu
assert paintify_gpu.bl_info["version"] == (0, 4, 0), paintify_gpu.__file__
bpy.ops.wm.save_userpref()
print("PAINTIFY_INSTALLED", paintify_gpu.bl_info["version"], paintify_gpu.__file__)
