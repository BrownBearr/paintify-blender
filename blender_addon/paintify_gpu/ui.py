"""Sidebar panels in the 3D Viewport."""

import bpy

from . import viewport


class PAINTIFY_PT_live(bpy.types.Panel):
    bl_label = "Paintify Live"
    bl_idname = "PAINTIFY_PT_live"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paintify"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.paintify_live
        running = viewport.running()
        layout.operator("paintify.toggle_live", text="Stop Live Paint" if running else "Start Live Paint",
                        icon="PAUSE" if running else "PLAY")
        layout.prop(settings, "preset")
        layout.prop(settings, "brush_size")
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
        fps, error = viewport.status()
        if running and fps:
            layout.label(text=f"Measured paint: {fps:.1f} FPS")
        if error:
            layout.label(text=error[:60], icon="ERROR")


class PAINTIFY_PT_render(bpy.types.Panel):
    bl_label = "Render"
    bl_idname = "PAINTIFY_PT_render"
    bl_parent_id = "PAINTIFY_PT_live"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paintify"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.paintify_live
        col = layout.column(align=True)
        col.operator("paintify.render_image", icon="RENDER_STILL")
        col.operator("paintify.render_animation", icon="RENDER_ANIMATION")
        layout.prop(settings, "hold_frames")
        space = context.space_data
        if space and space.region_3d.view_perspective != "CAMERA":
            layout.label(text="Camera view previews the render", icon="INFO")


def draw_render_menu(self, context):
    self.layout.separator()
    self.layout.operator("paintify.render_image", icon="RENDER_STILL")
    self.layout.operator("paintify.render_animation", icon="RENDER_ANIMATION")
