"""Resource interface of every shader stage, as data.

painter.py turns these into GPUShaderCreateInfo; tests/validate_shaders.py
turns them into Vulkan GLSL for glslangValidator, so the shaders can be
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
    "canvas": ("canvas.glsl", ["uIn", "uSrc", "uPrevSrc", "uFlow", "uPrevCanvas"],
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
    "blur": ("blur.glsl", ["uIn"], [("RGBA16F", "uOut", _W)],
             [("IVEC4", "uDir"), ("FLOAT", "uSigma")], False, (16, 16, 1)),
    "sobel": ("sobel.glsl", ["uRef"], [("RGBA16F", "uOut", _W)], [_SIZE], False, (16, 16, 1)),
    "errmap": ("errmap.glsl", ["uA", "uB"], [("R32F", "uOut", _W)],
               [("INT", "uMode"), _SIZE], False, (16, 16, 1)),
    "cells": ("cells.glsl", ["uErr", "uDiff"], [("RGBA32F", "uOut", _W)],
              [("IVEC4", "uGrid"), _SIZE], False, (16, 16, 1)),
    "trace": ("trace.glsl", ["uRef", "uCanvas", "uGrad", "uCells"],
              [("RGBA32F", "uVerts", _W), ("RGBA32F", "uHeads", _W)],
              [("VEC4", "uLayer"), ("IVEC4", "uSlots"), ("IVEC4", "uGrid")], True, (64, 1, 1)),
    "relax": ("relax.glsl", ["uSrc", "uGround"],
              [("RGBA32F", "uVerts", _RW), ("RGBA32F", "uHeads", _RW)],
              [("VEC4", "uRelax"), ("IVEC4", "uPool")], True, (64, 1, 1)),
    "impasto": ("impasto.glsl", ["uHeight"], [("RGBA16F", "uCanvas", _RW)],
                [_SIZE], True, (16, 16, 1)),
}

# The stroke rasteriser: vertex and fragment stage of one draw.
STROKE = {
    "vertex": "stroke_vert.glsl",
    "fragment": "stroke_frag.glsl",
    "samplers": ["uVerts", "uHeads", "uBrush", "uTooth", "uSnap"],
    "push": [("IVEC4", "uDraw"), ("VEC4", "uTex")],
    "vertex_in": [("FLOAT", "vid")],
    "smooth": [("VEC3", "vColor"), ("FLOAT", "vNorm"), ("FLOAT", "vArcPx"),
               ("FLOAT", "vHw"), ("VEC2", "vTang")],
    "flat": [("FLOAT", "vREff"), ("FLOAT", "vTotalLen"), ("FLOAT", "vOpacity"),
             ("FLOAT", "vTexHash"), ("FLOAT", "vRadius")],
    "fragment_out": [("VEC4", "fragColor"), ("VEC4", "fragHeight")],
}

PARAMS_STRUCT = ("struct PaintParams {\n" +
                 "".join(f"  vec4 p{i};\n" for i in range(PARAMS_VEC4S)) + "};\n")
STYLE_STRUCT = ("struct BrushkitStyle { vec4 bk[33]; vec4 bkPal[16]; "
                "vec4 bkLayerA[8]; vec4 bkLayerB[8]; };\n")
STYLE_STAGES = {"canvas", "ground", "support", "stylefield", "finish", "post", "flat", "trace"}


def source(*names):
    return "\n".join((SHADER_DIR / name).read_text(encoding="utf-8") for name in names)


def compute_source(name):
    file, _samplers, _images, _push, uses_params, _group = COMPUTE[name]
    return source("common.glsl", *(["params.glsl"] if uses_params else []),
                  *(["style.glsl"] if name in STYLE_STAGES else []), file)


def stroke_sources():
    return (source("common.glsl", "params.glsl", "style.glsl", STROKE["vertex"]),
            source("common.glsl", "params.glsl", "style.glsl", "procedural.glsl", STROKE["fragment"]))
