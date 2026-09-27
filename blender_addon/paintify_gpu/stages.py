"""Resource interface of every shader stage, as data.

painter.py turns these into GPUShaderCreateInfo; tests/test_shaders.py
turns them into Vulkan and OpenGL GLSL for glslangValidator, so the shaders can be
checked by a strict compiler without Blender. Pure Python.
"""

from pathlib import Path

SHADER_DIR = Path(__file__).with_name("shaders")
PARAMS_VEC4S = 7

_W = frozenset({"WRITE"})
_RW = frozenset({"READ", "WRITE"})
_SIZE = ("IVEC2", "uSize")

# name: (source, samplers, images (format, name, access), push constants,
#        uses the PaintParams uniform buffer, local group size)
COMPUTE = {
    "copy": ("copy.glsl", ["uIn"], [("RGBA16F", "uOut", _W)],
             [("INT", "uMode"), _SIZE, ("VEC4", "uFill")], False, (16, 16, 1)),
    "mean": ("mean.glsl", ["uIn"], [("RGBA32F", "uOut", _W)],
             [("INT", "uMode"), _SIZE], False, (16, 16, 1)),
    "blur": ("blur.glsl", ["uIn", "uMask"], [("RGBA16F", "uOut", _W)],
             [("IVEC4", "uDir"), ("FLOAT", "uSigma"), ("INT", "uMasked")], False, (16, 16, 1)),
    "sobel": ("sobel.glsl", ["uRef", "uMask"], [("RGBA16F", "uOut", _W)],
              [_SIZE, ("INT", "uMasked")], False, (16, 16, 1)),
    "errmap": ("errmap.glsl", ["uA", "uB"], [("R32F", "uOut", _W)],
               [("INT", "uMode"), _SIZE], False, (16, 16, 1)),
    "cells": ("cells.glsl", ["uErr", "uDiff", "uMask"], [("RGBA32F", "uOut", _W)],
              [("IVEC4", "uGrid"), _SIZE, ("INT", "uMasked")], False, (16, 16, 1)),
    "trace": ("trace.glsl", ["uRef", "uCanvas", "uGrad", "uCells"],
              [("RGBA32F", "uVerts", _W), ("RGBA32F", "uHeads", _W)],
              [("VEC4", "uLayer"), ("IVEC4", "uSlots"), ("IVEC4", "uGrid")], True, (64, 1, 1)),
    "relax": ("relax.glsl", ["uSrc", "uGround"],
              [("RGBA32F", "uVerts", _RW), ("RGBA32F", "uHeads", _RW)],
              [("VEC4", "uRelax"), ("IVEC4", "uPool")], True, (64, 1, 1)),
    "impasto": ("impasto.glsl", ["uHeight"], [("RGBA16F", "uCanvas", _RW)],
                [_SIZE], True, (16, 16, 1)),
    # Paintify Scene: strokes that belong to objects. See scene.py.
    "select": ("select.glsl", ["uA", "uB", "uGPos"], [("RGBA16F", "uOut", _W)],
               [_SIZE], False, (16, 16, 1)),
    "copy32": ("copy32.glsl", ["uIn"], [("RGBA32F", "uOut", _W)], [_SIZE], False, (16, 16, 1)),
    "shadow": ("shadow.glsl", ["uGDepth", "uIn"], [("R32F", "uOut", _W)],
               [("IVEC4", "uShadow")], True, (16, 16, 1)),
    "scene_cells": ("scene_cells.glsl", ["uErr", "uCover", "uGPos"],
                    [("RGBA32F", "uOut", _W)], [("IVEC4", "uGrid"), _SIZE], False, (16, 16, 1)),
    "lift_count": ("lift_count.glsl", ["uVerts", "uGPos", "uGDepth", "uShadow"],
                   [("RGBA32F", "uHeads", _RW), ("R32F", "uFlags", _W)],
                   [("IVEC4", "uRange")], True, (64, 1, 1)),
    "scan": ("scan.glsl", ["uFlags"], [("RGBA32F", "uBlocks", _RW), ("RGBA32F", "uCounter", _RW)],
             [("IVEC4", "uScan")], False, (64, 1, 1)),
    "lift_write": ("lift_write.glsl",
                   ["uVerts", "uHeads", "uFlags", "uBlocks", "uCounter", "uGPos", "uGDepth", "uRef",
                    "uTable"],
                   [("RGBA32F", "uAnchors", _W), ("RGBA32F", "uSHeads", _W)],
                   [("IVEC4", "uRange"), ("IVEC4", "uOrder"), ("VEC4", "uView")], True, (64, 1, 1)),
}

# Draws: vertex and fragment stage of one pipeline each. Every source list
# starts with common.glsl; "params" adds the PaintParams uniform buffer.
_STROKE_VARYINGS = {
    "smooth": [("VEC3", "vColor"), ("FLOAT", "vNorm"), ("FLOAT", "vArcPx"), ("FLOAT", "vVis")],
    "flat": [("FLOAT", "vREff"), ("FLOAT", "vTotalLen"), ("FLOAT", "vOpacity"),
             ("FLOAT", "vTexHash")],
    "fragment_out": [("VEC4", "fragColor"), ("VEC4", "fragHeight")],
}

# The stroke rasteriser for strokes traced this frame.
STROKE = dict(
    vertex=["stroke_vert.glsl"], fragment=["stroke_frag.glsl"], params=True,
    samplers=["uVerts", "uHeads", "uBrush"],
    push=[("IVEC4", "uDraw"), ("VEC4", "uTex")],
    vertex_in=[("FLOAT", "vid")], **_STROKE_VARYINGS,
)

# Paintify Scene: stored strokes, reprojected from object or world space.
SCENE_STROKE = dict(
    vertex=["table.glsl", "scene_stroke_vert.glsl"], fragment=["stroke_frag.glsl"], params=True,
    defines=["SCENE_STROKE"],
    samplers=["uAnchors", "uSHeads", "uBrush", "uRef", "uGDepth", "uTable", "uErr", "uShadow"],
    push=[("IVEC4", "uDraw"), ("VEC4", "uTex"), ("VEC4", "uView")],
    vertex_in=[("FLOAT", "vid")],
    smooth=_STROKE_VARYINGS["smooth"] + [("FLOAT", "vDepth"), ("FLOAT", "vDepthTol")],
    flat=_STROKE_VARYINGS["flat"], fragment_out=_STROKE_VARYINGS["fragment_out"],
)

# Paintify Scene's G-buffer of the scene's geometry.
GBUFFER = dict(
    vertex=["gbuffer_vert.glsl"], fragment=["gbuffer_frag.glsl"], params=False,
    samplers=[], push=[("MAT4", "uMVP"), ("VEC4", "uViewZ"), ("VEC4", "uSlot")],
    vertex_in=[("VEC3", "pos")], smooth=[("VEC3", "vLocal"), ("FLOAT", "vDepth")], flat=[],
    fragment_out=[("VEC4", "gPos"), ("VEC4", "gDepth")],
)

GRAPHICS = {"stroke": STROKE, "scene_stroke": SCENE_STROKE, "gbuffer": GBUFFER}

PARAMS_STRUCT = ("struct PaintParams {\n" +
                 "".join(f"  vec4 p{i};\n" for i in range(PARAMS_VEC4S)) + "};\n")


def source(*names):
    return "\n".join((SHADER_DIR / name).read_text(encoding="utf-8") for name in names)


def compute_source(name):
    file, samplers, _images, _push, uses_params, _group = COMPUTE[name]
    return source("common.glsl", *(["params.glsl"] if uses_params else []),
                  *(["table.glsl"] if "uTable" in samplers else []), file)


def graphics_sources(spec):
    """(vertex, fragment) source of a GRAPHICS pipeline, after its defines."""
    defines = "".join(f"#define {name}\n" for name in spec.get("defines", ()))
    head = ["common.glsl"] + (["params.glsl"] if spec["params"] else [])
    return (defines + source(*head, *spec["vertex"]),
            defines + source(*head, *spec["fragment"]))
