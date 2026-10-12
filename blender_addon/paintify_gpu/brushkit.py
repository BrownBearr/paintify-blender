"""Brushkit material definitions and the shared, version 1 .sbr settings format."""

from dataclasses import replace
import json
import math
from pathlib import Path
import re

DATA = json.loads(Path(__file__).with_name("brushkit_data.json").read_text())
STYLE_FIELDS = tuple(DATA["fields"])
STYLE_INDEX = {name: i for i, name in enumerate(STYLE_FIELDS)}
DEFAULT_BLOCK = tuple(DATA["defaults"])
BRUSHES = {entry["key"]: entry for entry in DATA["brushes"]}
BRUSH_FIELDS = STYLE_FIELDS[3:33]  # width, shape, load, pickup and relief
RADIUS_SETS = {
    "balanced": (8.0, 4.0, 2.0), "broad": (12.0, 6.0, 3.0),
    "fine": (6.0, 3.0, 1.5), "large_wash": (20.0, 10.0), "tiny_marks": (4.0, 2.0),
}


def select_brush(key, block=DEFAULT_BLOCK):
    """Change the brush material without resetting placement, colour or finish."""
    values = list(block)
    recipe = BRUSHES[key]["values"]
    for name in BRUSH_FIELDS + ("brushModel", "seed"):
        index = STYLE_INDEX[name]
        values[index] = recipe[index]
    values[2] = 0.0
    if key != "none":
        values[0] = 1.0
        if values[76] <= 0:
            values[76] = 0.5
    else:
        if values[76] == 0.5:
            values[76] = 0.0
        values[0] = float(values[33:121] != list(DEFAULT_BLOCK[33:121]) or
                          values[123:] != list(DEFAULT_BLOCK[123:]))
    return tuple(values)


def style_values(look, scale=1.0, frame=0):
    values = list(look.style_block or select_brush(look.brush_family))
    # Distances in the shared file are reference pixels; keep preview/render framing equal.
    for name in ("edgeSoft", "groovePx", "patchCell", "perturbScale", "curlScale",
                 "waveLen", "supportScale", "crackleSize", "licLength", "contourWidth",
                 "contourWobble", "contourSigma", "outlineWidth", "halftoneSpacing",
                 "causticScale", "rainLength", "facetCell"):
        values[STYLE_INDEX[name]] *= scale
    values[STYLE_INDEX["time"]] = float(frame)
    values[STYLE_INDEX["lightY"]] *= -1.0
    return tuple(values)


CORE_KEYS = {
    "threshold": "threshold", "max-length": "max_length", "min-length": "min_length",
    "curvature": "curvature", "grid-factor": "grid_factor", "opacity": "stroke_opacity",
    "tensor-sigma": "tensor_sigma", "jitter-hue": "jitter_hue", "jitter-sat": "jitter_sat",
    "jitter-val": "jitter_val", "size-jitter": "size_jitter", "angle-jitter": "angle_jitter",
    "opacity-jitter": "opacity_jitter", "brush-texture": "brush_texture",
    "texture-taper": "texture_taper", "dry-brush": "dry_brush", "impasto": "impasto",
    "impasto-light": "impasto_light", "light-angle": "light_angle",
    "temporal-diff": "temporal_diff", "jitter-per-frame": "jitter_per_frame",
    "relax-area": "relax_area", "relax-move": "relax_move", "relax-candidates": "relax_candidates",
    "relax-remove": "relax_remove", "relax-iterations": "relax", "relax-subpasses": "relax_subpasses",
    "etf-iterations": "etf", "etf-radius": "etf_radius", "flow-levels": "flow_levels",
    "flow-iterations": "flow_iterations", "fresh-paint": "fresh_paint",
    "passes": "passes", "bristle-density": "bristle_density",
}
INT_FIELDS = {"relax", "relax_subpasses", "relax_candidates", "etf", "flow_levels",
              "flow_iterations", "passes"}


def loads(text, base=None):
    from .looks import Look
    base = base or Look(preset="balanced")
    changes = {}
    block = None
    layers = {}
    for line in text.splitlines():
        parts = line.split('#', 1)[0].split()
        if not parts:
            continue
        key, *tokens = parts
        if not tokens:
            raise ValueError(f"Missing value for {key}")
        if key == "version":
            if tokens != ["1"]:
                raise ValueError("Unsupported Brushkit settings version")
        elif key == "style":
            if tokens[0] not in BRUSHES:
                raise ValueError(f"Unknown brush family: {tokens[0]}")
            changes["brush_family"] = tokens[0]
        elif key == "underpaint":
            if tokens[0] not in ("none", "blur", "average"):
                raise ValueError("Unknown underpaint")
            changes["underpaint"] = tokens[0]
        elif key == "radii":
            radii = tuple(float(v) for v in re.split(r'[,;\s]+', ' '.join(tokens)) if v)
            if not 1 <= len(radii) <= 8 or any(not math.isfinite(v) or v < 1 for v in radii):
                raise ValueError("Radii must contain 1-8 finite values of at least 1")
            changes["radii"] = tuple(sorted(radii, reverse=True))
        elif key == "style-block":
            block = tuple(float(v) for v in tokens)
            if len(block) != len(DEFAULT_BLOCK) or not all(math.isfinite(v) for v in block):
                raise ValueError("Invalid Brushkit style block")
        elif key == "layer":
            if len(tokens) != 7 or not 0 <= int(tokens[0]) < 8:
                raise ValueError("Invalid layer settings")
            layer = tuple(float(v) for v in tokens[1:])
            if any(math.isinf(v) for v in layer):
                raise ValueError("Infinite layer setting")
            layers[int(tokens[0])] = layer
        elif key in CORE_KEYS:
            value = float(tokens[0])
            if not math.isfinite(value):
                raise ValueError(f"Invalid value for {key}")
            name = CORE_KEYS[key]
            changes[name] = int(value) if name in INT_FIELDS else value
        else:
            raise ValueError(f"Unknown Brushkit setting: {key}")
    changes["style_block"] = block or select_brush(changes.get("brush_family", base.brush_family))
    changes["layer_specs"] = tuple(layers.get(i, (math.nan,) * 6)
                                   for i in range(max(layers, default=-1) + 1))
    return replace(base, **changes)


def dumps(look):
    lines = ["# Brushkit parameters", "version 1", "",
             "radii " + ', '.join(format(v, '.9g') for v in look.style.radii),
             "underpaint " + look.style.underpaint]
    for key, name in CORE_KEYS.items():
        value = getattr(look, name)
        if value is None:
            if name in ("jitter_hue", "jitter_sat", "jitter_val"):
                value = look.style.jitter[("jitter_hue", "jitter_sat", "jitter_val").index(name)]
            else:
                value = getattr(look.style, {"max_length": "max_len", "min_length": "min_len",
                                            "stroke_opacity": "opacity"}.get(name, name), 0)
        lines.append(f"{key} {value:.9g}")
    block = look.style_block or select_brush(look.brush_family)
    if block[0] > 0.5:
        lines.append("style " + look.brush_family)
        for index, layer in enumerate(look.layer_specs):
            lines.append(f"layer {index} " + ' '.join(format(v, '.9g') for v in layer))
        lines.append("style-block " + ' '.join(format(v, '.9g') for v in block))
    return '\n'.join(lines) + '\n'
