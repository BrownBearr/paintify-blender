"""Resource interface of every shader stage, as data.

painter.py turns these into GPUShaderCreateInfo; tests/validate_shaders.py
turns them into Vulkan GLSL for glslangValidator, so the shaders can be
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
    "samplers": ["uVerts", "uHeads", "uBrush"],
    "push": [("IVEC4", "uDraw"), ("VEC4", "uTex")],
    "vertex_in": [("FLOAT", "vid")],
    "smooth": [("VEC3", "vColor"), ("FLOAT", "vNorm"), ("FLOAT", "vArcPx")],
    "flat": [("FLOAT", "vREff"), ("FLOAT", "vTotalLen"), ("FLOAT", "vOpacity"),
             ("FLOAT", "vTexHash")],
    "fragment_out": [("VEC4", "fragColor"), ("VEC4", "fragHeight")],
}

PARAMS_STRUCT = ("struct PaintParams {\n" +
                 "".join(f"  vec4 p{i};\n" for i in range(PARAMS_VEC4S)) + "};\n")


def source(*names):
    return "\n".join((SHADER_DIR / name).read_text(encoding="utf-8") for name in names)


def compute_source(name):
    file, _samplers, _images, _push, uses_params, _group = COMPUTE[name]
    return source("common.glsl", *(["params.glsl"] if uses_params else []), file)


def stroke_sources():
    return (source("common.glsl", "params.glsl", STROKE["vertex"]),
            source("common.glsl", "params.glsl", STROKE["fragment"]))
