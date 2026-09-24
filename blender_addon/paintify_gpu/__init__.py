"""Paintify GPU compositor add-on for Blender 4.2+."""

bl_info = {
    "name": "Paintify GPU",
    "author": "BrownBearr",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Compositor > Add > Paintify GPU",
    "description": "Paint images and video using the independent GPU Hertzmann renderer",
    "category": "Node",
}

from pathlib import Path

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty

from . import engine


def _suggest_output(source):
    path = Path(bpy.path.abspath(source))
    suffix = ".mp4" if path.suffix.lower() in engine.VIDEO_SUFFIXES else ".png"
    return str(path.with_name(path.stem + "_paintified" + suffix))


class PAINTIFY_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    renderer_path: StringProperty(
        name="GPU Renderer", subtype="FILE_PATH",
        description="Path to this repository's built gpu-sbr executable",
    )

    def draw(self, context):
        self.layout.prop(self, "renderer_path")
        self.layout.label(text="Build the backend first with tools\\build.bat")


class PAINTIFY_CompositorNode(bpy.types.CompositorNodeCustomGroup):
    bl_idname = "PAINTIFY_CompositorNode"
    bl_label = "Paintify GPU"
    bl_icon = "BRUSH_DATA"

    source_path: StringProperty(name="Input image or video", subtype="FILE_PATH")
    output_path: StringProperty(name="Output file", subtype="FILE_PATH")
    preset: EnumProperty(name="Style", items=[(p, p.title(), "") for p in sorted(engine.PRESETS)], default="impressionist")
    threshold: FloatProperty(name="Threshold", default=50, min=0, max=255)
    curvature: FloatProperty(name="Curvature", default=1, min=0, max=1)
    brush_texture: FloatProperty(name="Brush texture", default=0.45, min=0, max=1)
    impasto: FloatProperty(name="Impasto", default=0, min=0, max=1)
    impasto_light: FloatProperty(name="Impasto light", default=0, min=0, max=1)
    relax: IntProperty(name="Relaxation iterations", default=0, min=0, max=12)
    temporal_diff: FloatProperty(name="Video temporal stability", default=12, min=0, max=255)

    @classmethod
    def poll(cls, node_tree):
        return node_tree.bl_idname == "CompositorNodeTree"

    def init(self, context):
        group = bpy.data.node_groups.new("Paintify GPU Output", "CompositorNodeTree")
        group.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        image = group.nodes.new("CompositorNodeImage")
        image.name = "Paintify Result"
        image.location = (-220, 0)
        output = group.nodes.new("NodeGroupOutput")
        output.location = (40, 0)
        group.links.new(image.outputs["Image"], output.inputs["Image"])
        self.node_tree = group
        self.width = 240

    def copy(self, node):
        # A duplicated node must not change the original node's output image.
        self.node_tree = node.node_tree.copy()

    def free(self):
        group = self.node_tree
        if group and group.users == 1:
            bpy.data.node_groups.remove(group)

    def draw_buttons(self, context, layout):
        layout.prop(self, "source_path")
        layout.prop(self, "output_path")
        layout.prop(self, "preset")
        layout.prop(self, "threshold")
        layout.prop(self, "curvature")
        layout.prop(self, "brush_texture")
        layout.prop(self, "impasto")
        layout.prop(self, "impasto_light")
        layout.prop(self, "relax")
        if Path(bpy.path.abspath(self.source_path)).suffix.lower() in engine.VIDEO_SUFFIXES:
            layout.prop(self, "temporal_diff")
        action = layout.operator("paintify.paint_node", text="Paint / Refresh", icon="FILE_REFRESH")
        action.node_name = self.name
        layout.label(text="Connect Image output to Composite")


class PAINTIFY_OT_paint_node(bpy.types.Operator):
    bl_idname = "paintify.paint_node"
    bl_label = "Paint with GPU"
    bl_description = "Render the selected image or full video with the GPU backend"

    node_name: StringProperty()

    def execute(self, context):
        tree = context.scene.node_tree
        node = tree.nodes.get(self.node_name) if tree else None
        if not node or node.bl_idname != PAINTIFY_CompositorNode.bl_idname:
            self.report({"ERROR"}, "Paintify node not found in current scene")
            return {"CANCELLED"}
        preferences = context.preferences.addons[__package__].preferences
        renderer = bpy.path.abspath(preferences.renderer_path)
        source = bpy.path.abspath(node.source_path)
        destination = bpy.path.abspath(node.output_path) if node.output_path else _suggest_output(node.source_path)
        try:
            output = engine.paint(
                renderer, source, destination, preset=node.preset,
                threshold=node.threshold, curvature=node.curvature,
                brush_texture=node.brush_texture, impasto=node.impasto,
                impasto_light=node.impasto_light, relax=node.relax,
                temporal_diff=node.temporal_diff,
            )
            image_node = node.node_tree.nodes["Paintify Result"]
            old_image = image_node.image
            if old_image:
                image_node.image = None
                if old_image.users == 0:
                    bpy.data.images.remove(old_image)
            image_node.image = bpy.data.images.load(str(output), check_existing=False)
            image_node.image_user.use_auto_refresh = True
            if image_node.image.source == "MOVIE":
                image_node.image_user.frame_duration = image_node.image.frame_duration
            node.output_path = str(output)
            node.node_tree.update_tag()
            self.report({"INFO"}, f"Painted: {output}")
            return {"FINISHED"}
        except (ValueError, RuntimeError, OSError) as exc:
            self.report({"ERROR"}, str(exc)[:240])
            return {"CANCELLED"}


def _draw_add_menu(self, context):
    if context.space_data and context.space_data.tree_type == "CompositorNodeTree":
        self.layout.separator()
        op = self.layout.operator("node.add_node", text="Paintify GPU", icon="BRUSH_DATA")
        op.type = PAINTIFY_CompositorNode.bl_idname
        op.use_transform = True


CLASSES = (PAINTIFY_Preferences, PAINTIFY_CompositorNode, PAINTIFY_OT_paint_node)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.NODE_MT_add.append(_draw_add_menu)


def unregister():
    bpy.types.NODE_MT_add.remove(_draw_add_menu)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
