"""Load and save the same look files used by the standalone Brushkit editor."""

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import brushkit
from .settings import apply_look, look_from_settings


class PAINTIFY_OT_load_look(bpy.types.Operator, ImportHelper):
    bl_idname = "paintify.load_look"
    bl_label = "Load Look"
    bl_options = {"UNDO"}
    filename_ext = ".sbr"
    filter_glob: StringProperty(default="*.sbr", options={"HIDDEN"})

    def execute(self, context):
        try:
            from pathlib import Path
            look = brushkit.loads(Path(self.filepath).read_text(encoding="utf-8"))
            apply_look(context.scene.paintify_live, look)
        except (OSError, ValueError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Brushkit look loaded")
        return {"FINISHED"}


class PAINTIFY_OT_save_look(bpy.types.Operator, ExportHelper):
    bl_idname = "paintify.save_look"
    bl_label = "Save Look"
    filename_ext = ".sbr"
    filter_glob: StringProperty(default="*.sbr", options={"HIDDEN"})

    def execute(self, context):
        try:
            from pathlib import Path
            Path(self.filepath).write_text(brushkit.dumps(look_from_settings(context.scene.paintify_live)),
                                           encoding="utf-8")
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Brushkit look saved")
        return {"FINISHED"}


class PAINTIFY_OT_global_layers(bpy.types.Operator):
    bl_idname = "paintify.global_layers"
    bl_label = "Use Global Stroke Settings"
    bl_options = {"UNDO"}

    def execute(self, context):
        context.scene.paintify_live.layer_specs = "[]"
        return {"FINISHED"}


class PAINTIFY_OT_palette(bpy.types.Operator):
    bl_idname = "paintify.palette"
    bl_label = "Edit Palette"
    bl_options = {"UNDO"}
    action: StringProperty(default="ADD")

    def execute(self, context):
        settings = context.scene.paintify_live
        if self.action == "ADD" and len(settings.pigments) < 16:
            settings.pigments.add()
        elif self.action == "REMOVE" and settings.pigments:
            settings.pigments.remove(len(settings.pigments) - 1)
        settings.bk_enabled = True
        return {"FINISHED"}
