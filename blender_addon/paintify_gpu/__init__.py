"""Paintify Live: painterly strokes over the 3D Viewport and in final renders,
in screen space or attached to the scene's objects (Paintify Scene)."""

bl_info = {
    "name": "Paintify Live",
    "author": "BrownBearr",
    "version": (0, 4, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > Paintify",
    "description": "Live painterly overlay of the 3D Viewport, painted renders that match it, "
                   "and brushwork that stays on objects as they move",
    "category": "3D View",
}

import bpy
from bpy.props import PointerProperty

from . import painter, render, scene, settings, ui, viewport

CLASSES = (
    settings.PAINTIFY_LiveSettings,
    viewport.PAINTIFY_OT_toggle,
    viewport.PAINTIFY_OT_reset_scene,
    render.PAINTIFY_OT_render_image,
    render.PAINTIFY_OT_render_animation,
    ui.PAINTIFY_PT_live,
    ui.PAINTIFY_PT_render,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.paintify_live = PointerProperty(type=settings.PAINTIFY_LiveSettings)
    bpy.types.TOPBAR_MT_render.append(ui.draw_render_menu)
    scene.register()


def unregister():
    bpy.types.TOPBAR_MT_render.remove(ui.draw_render_menu)
    scene.unregister()
    viewport.stop()
    painter.release()
    del bpy.types.Scene.paintify_live
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
