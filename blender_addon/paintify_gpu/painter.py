"""Hertzmann stroke painter on Blender's `gpu` module.

A port of the standalone renderer (src/pipeline.cpp and shaders/). Blender
compiles the stages for whichever backend it runs on (Metal on macOS, Vulkan
or OpenGL elsewhere), so nothing outside Blender is needed. The same Painter
paints the viewport overlay and final renders, which is what keeps the two
matching.

Per frame: import the source, lay the underpaint, then per layer (coarse to
fine) build the Gaussian reference, its gradient, the Lab error against the
canvas and the per-cell reduction, and paint the layer in several passes of
seed+trace (compute) and stroke rasterisation (instanced triangle strips).
Relaxation and impasto lighting follow when enabled. Every texture keeps
Blender's orientation: row 0 is the bottom of the image.
"""

import gpu
from gpu_extras.batch import batch_for_shader

from . import brushes, stages
from .looks import brush_rows, draw_order_step, layer_radii, plan_layer

MAX_VERTS = 33
STROKES_PER_ROW = 128
MAX_STORE_ROWS = 16384
MAX_STROKES = STROKES_PER_ROW * MAX_STORE_ROWS
MAX_SIDE = 8192
GROUP = 16

# Standalone renderer defaults that the panel does not expose.
TEXTURE_TAPER = 0.4
LIGHT_ANGLE = 45.0
RELAX_AREA_WEIGHT = 0.06
RELAX_MOVE_SCALE = 0.8
RELAX_CANDIDATES = 6.0

_shaders = None


def _compute(name):
    _file, samplers, images, push, uses_params, group = stages.COMPUTE[name]
    info = gpu.types.GPUShaderCreateInfo()
    if uses_params:
        info.typedef_source(stages.PARAMS_STRUCT)
        info.uniform_buf(0, "PaintParams", "params")
    for slot, sampler in enumerate(samplers):
        info.sampler(slot, "FLOAT_2D", sampler)
    for slot, (fmt, image, access) in enumerate(images):
        info.image(slot, fmt, "FLOAT_2D", image, qualifiers=set(access))
    for kind, constant in push:
        info.push_constant(kind, constant)
    info.local_group_size(*group)
    info.compute_source(stages.compute_source(name))
    return gpu.shader.create_from_info(info)


def _stroke_shader():
    spec = stages.STROKE
    iface = gpu.types.GPUStageInterfaceInfo("paintify_stroke_iface")
    for kind, name in spec["smooth"]:
        iface.smooth(kind, name)
    for kind, name in spec["flat"]:
        iface.flat(kind, name)
    info = gpu.types.GPUShaderCreateInfo()
    info.typedef_source(stages.PARAMS_STRUCT)
    info.uniform_buf(0, "PaintParams", "params")
    for slot, sampler in enumerate(spec["samplers"]):
        info.sampler(slot, "FLOAT_2D", sampler)
    for kind, name in spec["push"]:
        info.push_constant(kind, name)
    for slot, (kind, name) in enumerate(spec["vertex_in"]):
        info.vertex_in(slot, kind, name)
    info.vertex_out(iface)
    for slot, (kind, name) in enumerate(spec["fragment_out"]):
        info.fragment_out(slot, kind, name)
    vertex, fragment = stages.stroke_sources()
    info.vertex_source(vertex)
    info.fragment_source(fragment)
    return gpu.shader.create_from_info(info)


class _Shaders:
    def __init__(self):
        for name in stages.COMPUTE:
            setattr(self, name, _compute(name))
        self.stroke = _stroke_shader()
        self.strip = batch_for_shader(self.stroke, "TRI_STRIP",
                                      {"vid": [float(i) for i in range(MAX_VERTS * 2)]})


def shaders():
    """Compiles every stage on first use. Needs an active GPU context."""
    global _shaders
    if _shaders is None:
        _shaders = _Shaders()
    return _shaders


def release():
    """Drops the compiled stages while the GPU context still exists."""
    global _shaders
    _shaders = None


def _groups(width, height, size=GROUP):
    return (-(-width // size), -(-height // size), 1)


def texture_from_pixels(pixels, width, height):
    """Uploads float RGBA pixels (bottom row first, any flat sequence or NumPy
    array of width * height * 4 values) as an RGBA16F texture."""
    data = gpu.types.Buffer("FLOAT", width * height * 4, pixels)
    return gpu.types.GPUTexture((width, height), format="RGBA16F", data=data)


class Painter:
    """Owns the render targets and temporal state for one stream of frames:
    one Painter for the viewport overlay, a separate one per render job."""

    def __init__(self):
        self._textures = {}
        self._framebuffer = None
        self._framebuffer_key = None
        self._store_rows = 0
        self._verts = None
        self._heads = None
        self._atlas = None
        self._atlas_key = None
        self._atlas_rows = ()
        self._have_prev = False
        self._prev_key = None
        self.size = (0, 0)
        self.canvas = None
        self.params = None

    def reset(self):
        """Forget the previous frame, so the next paint starts from scratch."""
        self._have_prev = False
        self._prev_key = None

    # --- resources ----------------------------------------------------------

    def _texture(self, key, size, fmt):
        tex = self._textures.get(key)
        if tex is None or (tex.width, tex.height) != tuple(size) or tex.format != fmt:
            tex = gpu.types.GPUTexture(size, format=fmt)
            self._textures[key] = tex
        return tex

    def _resize(self, width, height):
        if self.size != (width, height):
            self.size = (width, height)
            self.reset()
        size = (width, height)
        t = self._texture
        self.src = t("src", size, "RGBA16F")
        self.prev_src = t("prev_src", size, "RGBA16F")
        self.ref = t("ref", size, "RGBA16F")
        self.tmp = t("tmp", size, "RGBA16F")
        self.grad = t("grad", size, "RGBA16F")
        self.err = t("err", size, "R32F")
        self.diff = t("diff", size, "R32F")
        self.canvas = t("canvas", size, "RGBA16F")
        self.height = t("height", size, "RGBA16F")
        self.prev_canvas = t("prev_canvas", size, "RGBA16F")
        self.under = t("under", size, "RGBA16F")
        if self._framebuffer_key != size:
            self._framebuffer = gpu.types.GPUFrameBuffer(color_slots=(self.canvas, self.height))
            self._framebuffer_key = size

    def _ensure_store(self, strokes):
        rows = max(1, -(-strokes // STROKES_PER_ROW))
        if rows > self._store_rows:
            rows = min(MAX_STORE_ROWS, max(rows, self._store_rows * 3 // 2))
            self._verts = gpu.types.GPUTexture((STROKES_PER_ROW * MAX_VERTS, rows), format="RGBA32F")
            self._heads = gpu.types.GPUTexture((STROKES_PER_ROW * 2, rows), format="RGBA32F")
            self._store_rows = rows

    def _ensure_atlas(self, radii):
        rows = tuple(brush_rows(r) for r in radii)
        if self._atlas_key != rows:
            data, used = brushes.make_atlas(radii)
            height = brushes.TILE_ROWS_MAX * brushes.VARIANTS * len(radii)
            buf = gpu.types.Buffer("FLOAT", len(data), data)
            self._atlas = gpu.types.GPUTexture((brushes.TILE_W, height), format="R32F", data=buf)
            self._atlas_key = rows
            self._atlas_rows = used

    # --- dispatch helpers ---------------------------------------------------

    def _run(self, shader, groups, samplers=(), images=(), ints=(), floats=(), params=False):
        shader.bind()
        for name, tex in samplers:
            shader.uniform_sampler(name, tex)
        for name, tex in images:
            shader.image(name, tex)
        if params:
            shader.uniform_block("params", self.params)
        for name, value in ints:
            shader.uniform_int(name, value)
        for name, value in floats:
            shader.uniform_float(name, value)
        gpu.compute.dispatch(shader, *groups)

    def _copy(self, src, dst, mode=1, fill=(1.0, 1.0, 1.0, 1.0)):
        w, h = self.size
        self._run(shaders().copy, _groups(w, h), [("uIn", src)], [("uOut", dst)],
                  [("uMode", mode), ("uSize", (w, h))], [("uFill", fill)])

    def _blur(self, src, dst, sigma):
        s = shaders()
        w, h = self.size
        self._run(s.blur, _groups(w, h), [("uIn", src)], [("uOut", self.tmp)],
                  [("uDir", (1, 0, w, h))], [("uSigma", sigma)])
        self._run(s.blur, _groups(w, h), [("uIn", self.tmp)], [("uOut", dst)],
                  [("uDir", (0, 1, w, h))], [("uSigma", sigma)])

    def _mean_fill(self):
        s = shaders()
        w, h = self.size
        tiles = _groups(w, h)[:2]
        blocks = self._texture("mean_blocks", tiles, "RGBA32F")
        total = self._texture("mean_total", (1, 1), "RGBA32F")
        self._run(s.mean, _groups(*tiles), [("uIn", self.src)], [("uOut", blocks)],
                  [("uMode", 0), ("uSize", (w, h))])
        self._run(s.mean, (1, 1, 1), [("uIn", blocks)], [("uOut", total)],
                  [("uMode", 1), ("uSize", tiles)])
        self._copy(total, self.canvas, mode=3)

    def _draw(self, first, count, layer):
        if count <= 0:
            return
        s = shaders()
        w, h = self.size
        radius = self._radii[layer]
        tex = (float(self._atlas_rows[layer]), float(layer * brushes.VARIANTS),
               brushes.TILE_W / max(16.0, radius * 4.0), 0.0)
        with self._framebuffer.bind():
            self._framebuffer.viewport_set(0, 0, w, h)
            blend = gpu.state.blend_get()
            depth = gpu.state.depth_test_get()
            gpu.state.blend_set("ALPHA_PREMULT")
            gpu.state.depth_test_set("NONE")
            gpu.state.face_culling_set("NONE")
            s.stroke.bind()
            s.stroke.uniform_sampler("uVerts", self._verts)
            s.stroke.uniform_sampler("uHeads", self._heads)
            s.stroke.uniform_sampler("uBrush", self._atlas)
            s.stroke.uniform_block("params", self.params)
            s.stroke.uniform_int("uDraw", (first, count, draw_order_step(count), 0))
            s.stroke.uniform_float("uTex", tex)
            s.strip.draw_instanced(s.stroke, instance_start=0, instance_count=count)
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)

    # --- the frame ----------------------------------------------------------

    def _make_params(self, look, width, height, frame):
        style = look.style
        values = (
            width, height, 1.0 / width, 1.0 / height,
            look.threshold, min(style.max_len, MAX_VERTS - 1), style.min_len, look.curvature,
            style.opacity, look.temporal_diff, 0.0, float(frame),
            style.jitter[0], style.jitter[1], style.jitter[2], 0.0,
            0.0, 0.0, look.brush_texture, TEXTURE_TAPER,
            look.impasto, look.impasto_light, LIGHT_ANGLE, 0.0,
            RELAX_AREA_WEIGHT, RELAX_MOVE_SCALE, RELAX_CANDIDATES, 0.0,
        )
        self.params = gpu.types.GPUUniformBuf(gpu.types.Buffer("FLOAT", len(values), values))

    def paint(self, source, width, height, look, scale=1.0, temporal=True, frame=0):
        """Paints `source`, a GPUTexture holding display-referred RGB of at
        least width x height. Returns the canvas texture (RGBA16F), valid
        until the next paint.

        `scale` multiplies the style's radii (see looks.stroke_scale). With
        `temporal`, cells whose source barely changed since the previous paint
        keep their strokes, provided the look and size are unchanged."""
        if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
            raise ValueError(f"Paint size {width}x{height} is unsupported")
        s = shaders()
        style = look.style
        radii = layer_radii(style, scale)
        self._radii = radii
        key = (look, radii)
        carried = self.size == (width, height) and self._have_prev
        self._resize(width, height)
        use_temporal = temporal and carried and self._prev_key == key and look.temporal_diff > 0
        self._ensure_atlas(radii)
        self._make_params(look, width, height, frame)
        w, h = width, height
        size_px = ("uSize", (w, h))

        # Keep the outgoing source for the temporal difference, then import.
        if carried:
            self._copy(self.src, self.prev_src)
        self._copy(source, self.src, mode=0)

        # Underpaint: last frame's paint, the coarsest blur, or the mean.
        if use_temporal:
            self._copy(self.prev_canvas, self.canvas)
            self._run(s.errmap, _groups(w, h), [("uA", self.src), ("uB", self.prev_src)],
                      [("uOut", self.diff)], [("uMode", 1), size_px])
        elif style.underpaint == "average":
            self._mean_fill()
        else:
            self._blur(self.src, self.ref, max(0.1, radii[0] * 0.5))
            self._copy(self.ref, self.canvas, mode=0)
        self.height.clear(format="FLOAT", value=(0.0, 0.0, 0.0, 0.0))

        plans = [plan_layer(w, h, r, style.grid_factor) for r in radii]
        pool_size = sum(p.passes * p.slots for p in plans)
        use_pool = 0 < look.relax and pool_size <= MAX_STROKES
        if use_pool:
            self._copy(self.canvas, self.under)
        strokes = pool_size if use_pool else max(p.slots for p in plans)
        if strokes > MAX_STROKES:
            raise ValueError("Too many strokes for this size; raise Brush size")
        self._ensure_store(strokes)

        regions = []
        next_slot = 0
        for layer, plan in enumerate(plans):
            self._blur(self.src, self.ref, max(0.1, plan.radius * 0.5))
            self._run(s.sobel, _groups(w, h), [("uRef", self.ref)], [("uOut", self.grad)],
                      [size_px])
            # Error once per layer against the canvas before this layer paints,
            # as worker.js builds `err` before its cell loop.
            self._run(s.errmap, _groups(w, h), [("uA", self.ref), ("uB", self.canvas)],
                      [("uOut", self.err)], [("uMode", 0), size_px])
            cells = self._texture(("cells", layer), (plan.cells_x, plan.cells_y), "RGBA32F")
            self._run(s.cells, _groups(plan.cells_x, plan.cells_y),
                      [("uErr", self.err), ("uDiff", self.diff if use_temporal else self.err)],
                      [("uOut", cells)],
                      [("uGrid", (plan.grid, int(use_temporal), plan.cells_x, plan.cells_y)),
                       size_px])
            layer_info = (float(layer), plan.radius, 1.0 if layer == 0 else 0.0, 0.0)
            grid_info = (plan.cells_x, plan.cells_y, int(use_temporal), 0)
            for pass_index in range(plan.passes):
                first = next_slot if use_pool else 0
                self._run(s.trace, (-(-plan.slots // 64), 1, 1),
                          [("uRef", self.ref), ("uCanvas", self.canvas), ("uGrad", self.grad),
                           ("uCells", cells)],
                          [("uVerts", self._verts), ("uHeads", self._heads)],
                          [("uSlots", (pass_index, plan.passes, plan.slots, first)),
                           ("uGrid", grid_info)],
                          [("uLayer", layer_info)], params=True)
                self._draw(first, plan.slots, layer)
                if use_pool:
                    regions.append((first, plan.slots, layer))
                    next_slot += plan.slots

        if use_pool:
            for iteration in range(look.relax):
                self._run(s.relax, (-(-next_slot // 64), 1, 1),
                          [("uSrc", self.src), ("uGround", self.under)],
                          [("uVerts", self._verts), ("uHeads", self._heads)],
                          [("uPool", (next_slot, 0, 0, 0))],
                          [("uRelax", (float(iteration), 0.0, 0.0, 0.0))], params=True)
                # A blended stroke cannot be taken back, so repaint the pool.
                self._copy(self.under, self.canvas)
                self.height.clear(format="FLOAT", value=(0.0, 0.0, 0.0, 0.0))
                for first, count, layer in regions:
                    self._draw(first, count, layer)

        if look.impasto_light > 0.0:
            self._run(s.impasto, _groups(w, h), [("uHeight", self.height)],
                      [("uCanvas", self.canvas)], [size_px], params=True)

        self._copy(self.canvas, self.prev_canvas)
        self._have_prev = True
        self._prev_key = key
        return self.canvas

    def read_pixels(self):
        """The canvas as a float32 NumPy array (height, width, 4), bottom row
        first."""
        import numpy as np

        return np.array(self.canvas.read(), dtype=np.float32, copy=True)
