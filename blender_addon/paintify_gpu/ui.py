"""Sidebar panels in the 3D Viewport."""

import bpy

from . import viewport
from .controls import GROUPS
from .settings import migrate_settings


def draw_live_button(layout):
    running = viewport.running()
    row = layout.row()
    row.scale_y = 1.4
    row.operator("paintify.toggle_live", text="Stop Live Paint" if running else "Start Live Paint",
                 icon="PAUSE" if running else "PLAY")


class PAINTIFY_LIVE_preferences(bpy.types.AddonPreferences):
    bl_idname = "paintify_gpu"

    def draw(self, context):
        draw_live_button(self.layout)
        settings = context.scene.paintify_live
        self.layout.prop(settings, "brush_family")
        self.layout.prop(settings, "brush_size")


class PAINTIFY_PT_live(bpy.types.Panel):
    bl_label = "Paintify Live"
    bl_idname = "PAINTIFY_PT_live"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paintify"
    bl_order = -90

    def draw(self, context):
        layout = self.layout
        settings = context.scene.paintify_live
        migrate_settings(settings)
        layout.use_property_split = True
        layout.use_property_decorate = False
        running = viewport.running()
        draw_live_button(layout)
        row = layout.row(align=True)
        row.operator("paintify.load_look", text="Load Look", icon="FILE_FOLDER")
        row.operator("paintify.save_look", text="Save Look", icon="FILE_TICK")
        layout.prop(settings, "inspector_tab", expand=True)
        if settings.inspector_tab == "RENDER":
            draw_render_settings(layout, settings)
            return
        layout.prop(settings, "brush_family")
        layout.prop(settings, "brush_size")
        layout.prop(settings, "stroke_opacity")
        if settings.layer_specs != "[]":
            layout.operator("paintify.global_layers", icon="RECOVER_LAST")
        fps, error = viewport.status()
        if running and fps:
            layout.label(text=f"Measured paint: {fps:.1f} FPS")
        if error:
            layout.label(text=error[:60], icon="ERROR")


class PAINTIFY_LIVE_PT_playback(bpy.types.Panel):
    bl_label = "Live Paint"
    bl_idname = "PAINTIFY_LIVE_PT_playback"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paintify"
    bl_order = -100
    bl_options = {"HIDE_HEADER"}

    def draw(self, context):
        draw_live_button(self.layout)


class PAINTIFY_PT_render(bpy.types.Panel):
    bl_label = "Render"
    bl_idname = "PAINTIFY_PT_render"
    bl_parent_id = "PAINTIFY_PT_live"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Paintify"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.paintify_live.inspector_tab == "RENDER"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.paintify_live
        draw_render_settings(layout, settings)
        space = context.space_data
        if space and space.region_3d.view_perspective != "CAMERA":
            layout.label(text="Camera view previews the render", icon="INFO")


def draw_render_settings(layout, settings):
    col = layout.column(align=True)
    col.operator("paintify.render_image", icon="RENDER_STILL")
    col.operator("paintify.render_animation", icon="RENDER_ANIMATION")
    for prop in ("hold_frames", "fps", "resolution", "opacity"):
        layout.prop(settings, prop)


def _draw_group(self, context):
    settings = context.scene.paintify_live
    layout = self.layout
    layout.use_property_split = True
    layout.use_property_decorate = False
    group = self.bl_label
    if group == "Stroke Settings":
        layout.prop(settings, "radius_set")
        if settings.radius_set == "custom":
            layout.prop(settings, "radii_text")
        for prop in ("threshold", "curvature", "max_length", "min_length", "grid_factor", "bk_enabled"):
            layout.prop(settings, prop)
        return
    elif group == "Brush":
        if settings.brush_family == "none":
            for prop in ("brush_texture", "texture_taper", "bristle_density", "dry_brush",
                         "impasto", "impasto_light", "light_angle"):
                layout.prop(settings, prop)
            return
        layout.prop(settings, "bk_tip")
    elif group == "Direction":
        layout.prop(settings, "tensor_sigma")
        layout.prop(settings, "etf")
        layout.prop(settings, "etf_radius")
        layout.prop(settings, "bk_fieldMode")
        layout.prop(settings, "bk_fallbackMode")
        layout.prop(settings, "bk_autoVortex")
    elif group == "Colour":
        row = layout.row(align=True)
        row.label(text="Palette")
        row.operator("paintify.palette", text="", icon="ADD").action = "ADD"
        row.operator("paintify.palette", text="", icon="REMOVE").action = "REMOVE"
        for pigment in settings.pigments:
            layout.prop(pigment, "color", text="")
    elif group == "Ground":
        layout.prop(settings, "underpaint")
        layout.prop(settings, "bk_groundMode")
        layout.prop(settings, "bk_strokesOff")
        layout.prop(settings, "ground_color")
        layout.prop(settings, "bk_support")
    elif group == "Finish":
        layout.prop(settings, "bk_finish")
        layout.prop(settings, "varnish_color")
    elif group == "Effects":
        layout.prop(settings, "contour_color")
    elif group == "Variation":
        for prop in ("jitter_hue", "jitter_sat", "jitter_val", "size_jitter", "angle_jitter",
                     "opacity_jitter", "jitter_per_frame"):
            layout.prop(settings, prop)
        return
    elif group == "Quality":
        for prop in ("passes", "relax", "relax_area", "relax_move", "relax_candidates",
                     "relax_remove", "relax_subpasses"):
            layout.prop(settings, prop)
        return
    elif group == "Motion":
        for prop in ("temporal_diff", "fresh_paint", "flow_levels", "flow_iterations",
                     "bk_temporalRefresh", "fps", "resolution", "opacity"):
            layout.prop(settings, prop)
        return
    for name, _label, _low, _high in GROUPS.get(group, ()):
        layout.prop(settings, "bk_" + name)


def _look_panel_visible(cls, context):
    return context.scene.paintify_live.inspector_tab == "LOOK"


LOOK_PANELS = tuple(type("PAINTIFY_LIVE_PT_" + name.lower().replace(" ", "_"), (bpy.types.Panel,), {
    "__module__": __name__,
    "bl_label": name, "bl_idname": "PAINTIFY_LIVE_PT_" + name.lower().replace(" ", "_"),
    "bl_parent_id": "PAINTIFY_PT_live", "bl_space_type": "VIEW_3D",
    "bl_region_type": "UI", "bl_category": "Paintify", "bl_options": {"DEFAULT_CLOSED"},
    "poll": classmethod(_look_panel_visible), "draw": _draw_group,
}) for name in ("Stroke Settings", *GROUPS, "Variation", "Quality", "Motion"))


def draw_render_menu(self, context):
    self.layout.separator()
    self.layout.operator("paintify.render_image", icon="RENDER_STILL")
    self.layout.operator("paintify.render_animation", icon="RENDER_ANIMATION")
