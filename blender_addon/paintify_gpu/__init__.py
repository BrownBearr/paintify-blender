"""Paintify Live: painterly strokes over the 3D Viewport and in final renders."""

bl_info = {
    "name": "Paintify Live",
    "author": "BrownBearr",
    "version": (0, 5, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Paintify",
    "description": "Live painterly overlay of the 3D Viewport, and painted renders that match it",
    "category": "3D View",
}

import sys

# Installing a zip over a running Paintify reloads only this file; Python
# would keep the previous version's submodules and the new classes would
# register against stale ones. Drop them so every reload is a clean import.
for _name in [n for n in sys.modules if n.startswith(__name__ + ".")]:
    del sys.modules[_name]
    # `from . import x` returns an attribute already on the package first.
    globals().pop(_name[len(__name__) + 1:].split(".")[0], None)

import bpy
from bpy.app.handlers import persistent
from bpy.props import PointerProperty

from . import look_files, painter, render, settings, ui, viewport

CLASSES = (
    ui.PAINTIFY_LIVE_preferences,
    settings.PAINTIFY_Pigment,
    settings.PAINTIFY_LiveSettings,
    look_files.PAINTIFY_OT_load_look,
    look_files.PAINTIFY_OT_save_look,
    look_files.PAINTIFY_OT_global_layers,
    look_files.PAINTIFY_OT_palette,
    viewport.PAINTIFY_OT_toggle,
    render.PAINTIFY_OT_render_image,
    render.PAINTIFY_OT_render_animation,
    ui.PAINTIFY_PT_live,
    ui.PAINTIFY_LIVE_PT_playback,
) + ui.LOOK_PANELS


@persistent
def _migrate_on_load(_filepath=None):
    settings.migrate_all_scenes()


def _migrate_now():
    settings.migrate_all_scenes()
    return None


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.paintify_live = PointerProperty(type=settings.PAINTIFY_LiveSettings)
    bpy.types.TOPBAR_MT_render.append(ui.draw_render_menu)
    bpy.app.handlers.load_post.append(_migrate_on_load)
    # The open file's scenes cannot be written during registration itself.
    bpy.app.timers.register(_migrate_now, first_interval=0.0)


def unregister():
    if _migrate_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_migrate_on_load)
    if bpy.app.timers.is_registered(_migrate_now):
        bpy.app.timers.unregister(_migrate_now)
    bpy.types.TOPBAR_MT_render.remove(ui.draw_render_menu)
    viewport.stop()
    painter.release()
    del bpy.types.Scene.paintify_live
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
