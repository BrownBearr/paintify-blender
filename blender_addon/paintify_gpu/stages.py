"""Resource interface of every shader stage, as data.

painter.py turns these into GPUShaderCreateInfo; tests/test_shaders.py
turns them into Vulkan and OpenGL GLSL for glslangValidator, so the shaders can be
checked by a strict compiler without Blender. Pure Python.
"""

from pathlib import Path

SHADER_DIR = Path(__file__).with_name("shaders")
PARAMS_VEC4S = 8

_W = frozenset({"WRITE"})
_RW = frozenset({"READ", "WRITE"})
_SIZE = ("IVEC2", "uSize")

# name: (source, samplers, images (format, name, access), push constants,
#        uses the PaintParams uniform buffer, local group size)
COMPUTE = {
    "downsample": ("downsample.glsl", ["uIn"], [("RGBA16F", "uOut", _W)],
                   [_SIZE, ("INT", "uLuma")], False, (16, 16, 1)),
    "max_reduce": ("max_reduce.glsl", ["uIn"], [("RGBA32F", "uOut", _W)],
                   [("INT", "uMode")], False, (16, 16, 1)),
    "etf": ("etf.glsl", ["uField", "uMax"], [("RGBA16F", "uOut", _W)],
            [], True, (16, 16, 1)),
    "flow": ("flow.glsl", ["uLumaPrev", "uLumaCur", "uFlowIn", "uSrcRgba"],
             [("RG16F", "uFlowOut", _W), ("R16F", "uLumaOut", _W)],
             [("INT", "uPass"), ("INT", "uLevel"), ("IVEC2", "uFlowSize"),
              ("INT", "uWindow")], True, (16, 16, 1)),
    "canvas": ("canvas.glsl", ["uIn", "uSrc", "uPrevSrc", "uFlow", "uPrevCanvas", "uMask"],
               [("RGBA16F", "uCanvas", _W), ("R32F", "uDiff", _W)],
               [("INT", "uPass"), ("INT", "uUseFlow"), ("FLOAT", "uFreshPaint"),
                ("VEC3", "uFill")], True, (16, 16, 1)),
    "ground": ("ground.glsl", ["uIn"], [("RGBA16F", "uOut", _W)], [], True, (16, 16, 1)),
    "support": ("support.glsl", [], [("R16F", "uTooth", _W)], [], True, (16, 16, 1)),
    "stylefield": ("stylefield.glsl", ["uGrad"], [("RGBA16F", "uOut", _W)],
                   [], True, (16, 16, 1)),
    "finish": ("finish.glsl", ["uColor", "uHeight", "uTooth"],
               [("RGBA16F", "uOut", _W)], [], True, (16, 16, 1)),
    "post": ("post.glsl", ["uColor", "uGrad", "uFlatS", "uToothS", "uSrc"],
             [("RGBA16F", "uOut", _RW)], [("INT", "uPass"), ("INT", "uFlatValid")],
             True, (16, 16, 1)),
    "flat": ("flat.glsl", ["uSrc"], [("RGBA16F", "uFlat", _RW), ("RGBA16F", "uCanvas", _W)],
             [("INT", "uPass")], True, (16, 16, 1)),
    "features": ("features.glsl", ["uRef", "uTensor"], [("RGBA16F", "uOut", _W)],
                 [("INT", "uPass")], True, (16, 16, 1)),
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
    "dilate": ("dilate.glsl", ["uIn"], [("R32F", "uOut", _W)],
               [("IVEC4", "uDir"), ("INT", "uRadius")], False, (16, 16, 1)),
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
# starts with common.glsl; "params" adds the PaintParams uniform buffer and
# "style" the Brushkit one with style.glsl.
_STROKE_VARYINGS = {
    "smooth": [("VEC3", "vColor"), ("FLOAT", "vNorm"), ("FLOAT", "vArcPx"),
               ("FLOAT", "vHw"), ("VEC2", "vTang"), ("FLOAT", "vVis")],
    "flat": [("FLOAT", "vREff"), ("FLOAT", "vTotalLen"), ("FLOAT", "vOpacity"),
             ("FLOAT", "vTexHash"), ("FLOAT", "vRadius")],
    "fragment_out": [("VEC4", "fragColor"), ("VEC4", "fragHeight")],
}

# The stroke rasteriser for strokes traced this frame.
# Brushkit's brush model (procedural.glsl) reads the paper tooth and a
# snapshot of the canvas under the stroke.
_BRUSHKIT_SAMPLERS = ["uTooth", "uSnap"]

STROKE = dict(
    vertex=["stroke_vert.glsl"], fragment=["procedural.glsl", "stroke_frag.glsl"],
    params=True, style=True,
    samplers=["uVerts", "uHeads", "uBrush"] + _BRUSHKIT_SAMPLERS,
    push=[("IVEC4", "uDraw"), ("VEC4", "uTex")],
    vertex_in=[("FLOAT", "vid")], **_STROKE_VARYINGS,
)

# Paintify Scene: stored strokes, reprojected from object or world space.
SCENE_STROKE = dict(
    vertex=["table.glsl", "scene_stroke_vert.glsl"],
    fragment=["procedural.glsl", "stroke_frag.glsl"], params=True, style=True,
    defines=["SCENE_STROKE"],
    samplers=["uAnchors", "uSHeads", "uBrush", "uRef", "uGDepth", "uTable", "uErr",
              "uShadow"] + _BRUSHKIT_SAMPLERS,
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
STYLE_STRUCT = ("struct BrushkitStyle { vec4 bk[33]; vec4 bkPal[16]; "
                "vec4 bkLayerA[8]; vec4 bkLayerB[8]; };\n")
STYLE_STAGES = {"canvas", "ground", "support", "stylefield", "finish", "post", "flat", "trace"}


def source(*names):
    return "\n".join((SHADER_DIR / name).read_text(encoding="utf-8") for name in names)


def compute_source(name):
    file, samplers, _images, _push, uses_params, _group = COMPUTE[name]
    return source("common.glsl", *(["params.glsl"] if uses_params else []),
                  *(["style.glsl"] if name in STYLE_STAGES else []),
                  *(["table.glsl"] if "uTable" in samplers else []), file)


def graphics_sources(spec):
    """(vertex, fragment) source of a GRAPHICS pipeline, after its defines."""
    defines = "".join(f"#define {name}\n" for name in spec.get("defines", ()))
    head = (["common.glsl"] + (["params.glsl"] if spec["params"] else []) +
            (["style.glsl"] if spec.get("style") else []))
    return (defines + source(*head, *spec["vertex"]),
            defines + source(*head, *spec["fragment"]))
