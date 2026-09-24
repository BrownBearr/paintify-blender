"""Brush tiles, ported from src/brush_atlas.cpp (itself brush-texture.js).

One tile per (radius index, variant): an across-width bristle profile times
low-frequency along-stroke noise, with a slight edge boost. Tiles are stacked
vertically into one TILE_W x (TILE_ROWS_MAX * tiles) single-channel atlas.
"""

import math

from .looks import brush_rows

TILE_W = 64
TILE_ROWS_MAX = 48
VARIANTS = 8
_MASK = 0xFFFFFFFF


class _Mulberry32:
    """worker.js `mulberry32`, with its 32-bit wraparound."""

    def __init__(self, seed):
        self.state = seed & _MASK

    def __call__(self):
        self.state = (self.state + 0x6D2B79F5) & _MASK
        s = self.state
        t = ((s ^ (s >> 15)) * (1 | s)) & _MASK
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & _MASK)) & _MASK) ^ t
        return ((t ^ (t >> 14)) & _MASK) / 4294967296.0


def _round(x):
    return int(math.floor(x + 0.5))


def make_tile(rows, density, rand):
    """brush-texture.js `makeBrushTile`, `rows` x TILE_W values, row-major."""
    profile = [1.0] * rows
    for _ in range(max(2, _round(density * rows / 24.0))):
        centre = rand() * rows
        width = 0.6 + rand() * 1.6
        depth = 0.3 + rand() * 0.55
        for y in range(rows):
            d = (y - centre) / width
            profile[y] -= depth * math.exp(-d * d)

    # Cosine-interpolated control points, wrapped so the tile repeats along a
    # stroke. Each row has its own phase so streaks break up unevenly.
    ctrl = [rand() for _ in range(8)]
    ctrl.append(ctrl[0])
    phase = [rand() * TILE_W for _ in range(rows)]

    out = []
    for y in range(rows):
        v_abs = abs(y / (rows - 1) * 2.0 - 1.0) if rows > 1 else 0.0
        edge = 1.0 + 0.22 * max(0.0, (v_abs - 0.6) / 0.4)
        p = min(1.15, max(0.04, profile[y])) * edge
        for x in range(TILE_W):
            fx = math.fmod(x + phase[y], TILE_W) / TILE_W * 8.0
            i0 = int(fx)
            f = fx - i0
            cf = (1.0 - math.cos(f * math.pi)) * 0.5
            n = ctrl[i0] * (1.0 - cf) + ctrl[i0 + 1] * cf
            out.append(min(1.2, max(0.0, p * (0.78 + 0.44 * n))))
    return out


_tile_cache = {}


def tile(radius_index, variant, rows, density=10.0):
    key = (radius_index, variant, rows, density)
    cached = _tile_cache.get(key)
    if cached is None:
        # Same seed expression as makeBrushTextures.
        seed = 0x9E3779B9 ^ ((radius_index * 131 + variant * 7919) & _MASK)
        cached = _tile_cache[key] = make_tile(rows, density, _Mulberry32(seed))
    return cached


def make_atlas(radii, density=10.0):
    """Returns (flat values, rows used per radius). Tile i * VARIANTS + v holds
    radius i, variant v; rows past `rows[i]` stay zero and are never read."""
    rows_used = [brush_rows(r) for r in radii]
    data = []
    padding = [0.0] * TILE_W
    for index, rows in enumerate(rows_used):
        for variant in range(VARIANTS):
            data.extend(tile(index, variant, rows, density))
            data.extend(padding * (TILE_ROWS_MAX - rows))
    return data, rows_used
