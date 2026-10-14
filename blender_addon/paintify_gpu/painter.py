"""Hertzmann stroke painter on Blender's `gpu` module.

A port of the paintify-GPU renderer (src/pipeline.cpp and shaders/). Blender
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

import math

import gpu
from gpu_extras.batch import batch_for_shader

from . import brushes, stages
from .brushkit import style_values, STYLE_INDEX
from .looks import brush_rows, draw_order_step, layer_radii, plan_layer

MAX_VERTS = 33
STROKES_PER_ROW = 128
MAX_STORE_ROWS = 16384
MAX_STROKES = STROKES_PER_ROW * MAX_STORE_ROWS
MAX_SIDE = 8192
GROUP = 16

# How far, in coarsest-brush radii, a source change clears and repaints old
# paint around it. Strokes leak past their own cell; less than this leaves
# faint trails behind moving objects.
TRAIL_REACH = 2.0

_shaders = None


def _compute(name):
    _file, samplers, images, push, uses_params, group = stages.COMPUTE[name]
    info = gpu.types.GPUShaderCreateInfo()
    if uses_params:
        info.typedef_source(stages.PARAMS_STRUCT +
                            (stages.STYLE_STRUCT if name in stages.STYLE_STAGES else ""))
        info.uniform_buf(0, "PaintParams", "params")
    if name in stages.STYLE_STAGES:
        info.uniform_buf(1, "BrushkitStyle", "brushkit")
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
    info.typedef_source(stages.PARAMS_STRUCT + stages.STYLE_STRUCT)
    info.uniform_buf(0, "PaintParams", "params")
    info.uniform_buf(1, "BrushkitStyle", "brushkit")
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
        self.with_style = tuple(getattr(self, name) for name in stages.STYLE_STAGES)
        self._strips = {}

    def strip(self, points):
        """A strip with two vertices per point. Sized to the longest stroke the
        look can trace, since every instance runs every vertex."""
        batch = self._strips.get(points)
        if batch is None:
            batch = self._strips[points] = batch_for_shader(
                self.stroke, "TRI_STRIP", {"vid": [float(i) for i in range(points * 2)]})
        return batch


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


def read_texture_pixels(texture):
    import numpy as np
    data = texture.read()
    # Blender 5.1 advertises column-major strides for multidimensional Buffers.
    # Flatten before NumPy sees them; the texture bytes themselves are row-major.
    data.dimensions = texture.width * texture.height * 4
    return np.array(data, dtype=np.float32, copy=True).reshape(texture.height, texture.width, 4)


class Painter:
    """Owns the render targets and temporal state for one stream of frames:
    one Painter for the viewport overlay, a separate one per render job."""

    def __init__(self):
        self._textures = {}
        self._framebuffers = {}
        self._framebuffer_key = None
        self._flip = 0
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
        self.style_params = None
        self.output = None
        self.render_count = 0
        self._vortex = None

    def reset(self):
        """Forget the previous frame, so the next paint starts from scratch."""
        self._have_prev = False
        self._prev_key = None
        self._vortex = None

    # --- resources ----------------------------------------------------------

    def _texture(self, key, size, fmt):
        tex = self._textures.get(key)
        if tex is None or (tex.width, tex.height) != tuple(size) or tex.format != fmt:
            tex = gpu.types.GPUTexture(size, format=fmt)
            if hasattr(tex, "filter_mode"):
                tex.filter_mode(True)
            self._textures[key] = tex
        return tex

    def _resize(self, width, height):
        if self.size != (width, height):
            self.size = (width, height)
            self.reset()
        size = (width, height)
        t = self._texture
        # Source and canvas ping-pong between two textures each, so the
        # previous frame's copies are kept by swapping roles, not by copying.
        self._flip ^= 1
        a, b = ("a", "b") if self._flip else ("b", "a")
        self.src = t(("src", a), size, "RGBA16F")
        self.prev_src = t(("src", b), size, "RGBA16F")
        self.canvas = t(("canvas", a), size, "RGBA16F")
        self.prev_canvas = t(("canvas", b), size, "RGBA16F")
        self.ref = t("ref", size, "RGBA16F")
        self.tmp = t("tmp", size, "RGBA16F")
        self.grad = t("grad", size, "RGBA16F")
        self.err = t("err", size, "R32F")
        self.diff = t("diff", size, "R32F")
        self.diff_tmp = t("diff_tmp", size, "R32F")
        self.height = t("height", size, "RGBA16F")
        self.under = t("under", size, "RGBA16F")
        self.tooth = t("tooth", size, "R16F")
        self.snap = t("snap", size, "RGBA16F")
        self.flat = t("flat", size, "RGBA16F")
        self.final = t("final", size, "RGBA16F")
        self.post_tmp = t("post_tmp", size, "RGBA16F")
        self.field_tmp = t("field_tmp", size, "RGBA16F")
        self.tensor = t("tensor", size, "RGBA16F")
        if self._framebuffer_key != size:
            self._framebuffers = {}
            self._framebuffer_key = size
        if a not in self._framebuffers:
            self._framebuffers[a] = gpu.types.GPUFrameBuffer(color_slots=(self.canvas, self.height))
        self._framebuffer = self._framebuffers[a]

    def _ensure_store(self, strokes):
        rows = max(1, -(-strokes // STROKES_PER_ROW))
        if rows > self._store_rows:
            rows = min(MAX_STORE_ROWS, max(rows, self._store_rows * 3 // 2))
            self._verts = gpu.types.GPUTexture((STROKES_PER_ROW * MAX_VERTS, rows), format="RGBA32F")
            self._heads = gpu.types.GPUTexture((STROKES_PER_ROW * 2, rows), format="RGBA32F")
            self._store_rows = rows

    def _ensure_atlas(self, radii, density=10.0):
        rows = (tuple(brush_rows(r) for r in radii), density)
        if self._atlas_key != rows:
            data, used = brushes.make_atlas(radii, density)
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
        if shader in shaders().with_style:
            shader.uniform_block("brushkit", self.style_params)
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

    def _flow(self, look):
        w, h = self.size
        s = shaders()
        pyramid = []
        prev, cur = self.prev_src, self.src
        for level in range(1, look.flow_levels + 2):
            size = (max(1, w >> level), max(1, h >> level))
            targets = []
            for name, source in (("prev", prev), ("cur", cur)):
                target = self._texture(("luma", name, level), size, "RGBA16F")
                self._run(s.downsample, _groups(*size), [("uIn", source)], [("uOut", target)],
                          [("uSize", size), ("uLuma", int(level == 1))])
                targets.append(target)
            prev, cur = targets
            pyramid.append(targets)
        size = (max(1, w // 4), max(1, h // 4))
        flow = self._texture("flow", size, "RG16F")
        scratch = self._texture("flow_scratch", size, "RG16F")
        dummy = self._texture("luma_dummy", (1, 1), "R16F")
        flow.clear(format="FLOAT", value=(0.0, 0.0))
        for level in range(look.flow_levels + 1, 1, -1):
            prev, cur = pyramid[level - 1]
            for iteration in range(look.flow_iterations + 1):
                self._run(s.flow, _groups(*size), [("uLumaPrev", prev), ("uLumaCur", cur),
                          ("uFlowIn", flow), ("uSrcRgba", self.src)],
                          [("uFlowOut", scratch), ("uLumaOut", dummy)],
                          [("uPass", 2 if iteration == look.flow_iterations else 1),
                           ("uLevel", level), ("uFlowSize", size), ("uWindow", 2)], params=True)
                flow, scratch = scratch, flow
        return flow

    def _track_vortex(self, block, smooth):
        import math
        import numpy as np
        source = self.src
        levels = max(0, int(math.floor(math.log2(max(self.size) / 16))))
        for level in range(levels):
            size = (max(1, source.width//2), max(1, source.height//2))
            target = self._texture(("vortex", level), size, "RGBA16F")
            self._run(shaders().downsample, _groups(*size), [("uIn", source)],
                      [("uOut", target)], [("uSize", size), ("uLuma", 0)])
            source = target
        pixels = read_texture_pixels(source)
        y, x = np.mgrid[:source.height, :source.width]
        u, v = (x+.5)/source.width, (y+.5)/source.height
        brightness = pixels[..., :3] @ np.array([.299, .587, .114]) - .15*((u-.5)**2+(v-.5)**2)
        py, px = np.unravel_index(brightness.argmax(), brightness.shape)
        center = np.array([u[py,px], v[py,px]])
        self._vortex = self._vortex + .08*(center-self._vortex) if smooth and self._vortex is not None else center
        values = list(block)
        values[STYLE_INDEX["vortexX"]:STYLE_INDEX["vortexY"]+1] = (self._vortex[0], 1-self._vortex[1])
        return tuple(values)

    def _maximum(self, source, mode):
        level = 0
        while True:
            size = (max(1, -(-source.width // 16)), max(1, -(-source.height // 16)))
            target = self._texture(("maximum", level), size, "RGBA32F")
            self._run(shaders().max_reduce, _groups(*size), [("uIn", source)],
                      [("uOut", target)], [("uMode", mode)])
            source, mode, level = target, 1, level+1
            if size == (1, 1):
                break
        return source

    def _etf(self, iterations):
        w, h = self.size
        source = self._maximum(self.grad, 0)
        for _ in range(iterations):
            self._run(shaders().etf, _groups(w, h), [("uField", self.grad), ("uMax", source)],
                      [("uOut", self.field_tmp)], params=True)
            self._copy(self.field_tmp, self.grad)

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
            s.stroke.uniform_sampler("uTooth", self.tooth)
            s.stroke.uniform_sampler("uSnap", self.snap)
            s.stroke.uniform_block("params", self.params)
            s.stroke.uniform_block("brushkit", self.style_params)
            s.stroke.uniform_int("uDraw", (first, count, draw_order_step(count), 0))
            s.stroke.uniform_float("uTex", tex)
            s.strip(self._points).draw_instanced(s.stroke, instance_start=0, instance_count=count)
            gpu.state.blend_set(blend)
            gpu.state.depth_test_set(depth)

    # --- the frame ----------------------------------------------------------

    def _make_params(self, look, width, height, frame, layer=0):
        style = look.style
        core = [look.threshold, min(style.max_len, MAX_VERTS - 1), style.min_len,
                look.curvature, style.opacity, style.grid_factor]
        if layer < len(look.layer_specs):
            import math
            for index, value in enumerate(look.layer_specs[layer]):
                if math.isfinite(value):
                    core[(1, 2, 0, 3, 4, 5)[index]] = value
        values = (
            width, height, 1.0 / width, 1.0 / height,
            *core[:4],
            core[4], look.temporal_diff, look.jitter_per_frame, float(frame),
            *style.jitter, look.size_jitter,
            look.angle_jitter, look.opacity_jitter, look.brush_texture, look.texture_taper,
            look.impasto, look.impasto_light, look.light_angle, look.dry_brush,
            look.relax_area, look.relax_move, look.relax_candidates, look.relax_remove,
            layer, look.etf_radius, look.fresh_paint, 0.0,
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
        # Trace stops after max_len steps (per layer when overridden) and
        # relaxation only shortens, so no stroke has more points than this.
        lengths = [style.max_len] + [spec[0] for spec in look.layer_specs
                                     if spec and math.isfinite(spec[0])]
        self._points = min(MAX_VERTS, int(min(max(lengths), MAX_VERTS - 1)) + 1)
        block = style_values(look, scale, frame)
        animated = (look.jitter_per_frame > .5 or block[STYLE_INDEX["rain"]] > 0 or
                    block[STYLE_INDEX["temporalRefresh"]] > 0)
        key = (look.cache_key, radii, frame if animated else 0)
        carried = self.size == (width, height) and self._have_prev
        if carried and self._prev_key == key and self.output is not None:
            self._copy(source, self.post_tmp, mode=0)
            self._run(s.errmap, _groups(width, height), [("uA", self.post_tmp), ("uB", self.src)],
                      [("uOut", self.diff)], [("uMode", 1), ("uSize", (width, height))])
            maximum = self._maximum(self.diff, 1)
            if read_texture_pixels(maximum)[0, 0, 0] == 0:
                return self.output
        self._resize(width, height)
        use_temporal = (temporal and carried and self._prev_key[:2] == key[:2]
                        and look.temporal_diff > 0)
        self.render_count += 1
        self._ensure_atlas(radii, look.bristle_density)
        self.style_params = gpu.types.GPUUniformBuf(gpu.types.Buffer("FLOAT", len(block), block))
        self._make_params(look, width, height, frame)
        w, h = width, height
        size_px = ("uSize", (w, h))

        # The swap in _resize already kept last frame's source in prev_src.
        self._copy(source, self.src, mode=0)
        if block[0] > .5 and block[STYLE_INDEX["autoVortex"]] > .5:
            block = self._track_vortex(block, use_temporal)
            self.style_params = gpu.types.GPUUniformBuf(gpu.types.Buffer("FLOAT", len(block), block))
        if block[0] > 0.5:
            self._run(s.support, _groups(w, h), images=[("uTooth", self.tooth)], params=True)
        else:
            self.tooth.clear(format="FLOAT", value=(0.5,))

        # Underpaint: last frame's paint, the coarsest blur, or the mean.
        # `ref_sigma` remembers which blur `ref` holds, so the first layer can
        # reuse it instead of blurring again.
        ref_sigma = None
        if use_temporal:
            flow = (self._flow(look) if look.flow_levels > 0 else
                    self._texture("flow_zero", (1, 1), "RG16F"))
            if look.flow_levels == 0:
                flow.clear(format="FLOAT", value=(0.0, 0.0))
                self._copy(self.prev_canvas, self.canvas)
            ref_sigma = max(0.1, radii[0] * .5)
            self._blur(self.src, self.ref, ref_sigma)
            samplers = [("uIn", self.ref), ("uSrc", self.src), ("uPrevSrc", self.prev_src),
                        ("uFlow", flow), ("uPrevCanvas", self.prev_canvas), ("uMask", self.err)]
            images = [("uCanvas", self.canvas), ("uDiff", self.diff)]
            for mode in ((3, 2) if look.flow_levels > 0 else (2,)):
                self._run(s.canvas, _groups(w, h), samplers, images,
                          [("uPass", mode), ("uUseFlow", int(look.flow_levels > 0))],
                          [("uFreshPaint", look.fresh_paint), ("uFill", (1.0, 1.0, 1.0))],
                          params=True)
            # Strokes reach past the cell they were seeded in, so a change
            # clears and repaints its neighbourhood, not just its own pixels.
            # Reusing old paint there is what left trails behind moving objects.
            reach = max(1, int(math.ceil(radii[0] * TRAIL_REACH)))
            self._run(s.dilate, _groups(w, h), [("uIn", self.diff)], [("uOut", self.err)],
                      [("uDir", (1, 0, w, h)), ("uRadius", reach)])
            self._run(s.dilate, _groups(w, h), [("uIn", self.err)], [("uOut", self.diff_tmp)],
                      [("uDir", (0, 1, w, h)), ("uRadius", reach)])
            self.diff, self.diff_tmp = self.diff_tmp, self.diff
            samplers[-1] = ("uMask", self.diff)
            self._run(s.canvas, _groups(w, h), samplers,
                      [("uCanvas", self.canvas), ("uDiff", self.diff_tmp)],
                      [("uPass", 5), ("uUseFlow", int(look.flow_levels > 0))],
                      [("uFreshPaint", look.fresh_paint), ("uFill", (1.0, 1.0, 1.0))],
                      params=True)
        elif style.underpaint == "average":
            self._mean_fill()
        elif style.underpaint == "none":
            self.canvas.clear(format="FLOAT", value=(1.0, 1.0, 1.0, 1.0))
        else:
            ref_sigma = max(0.1, radii[0] * 0.5)
            self._blur(self.src, self.ref, ref_sigma)
            self._copy(self.ref, self.canvas, mode=0)
        flat_ground = block[0] > .5 and block[STYLE_INDEX["groundMode"]] > 1.5
        flat_valid = block[0] > .5 and (flat_ground or any(block[STYLE_INDEX[name]] > 0 for name in
                                      ("watercolor", "outline", "halftone", "bokashi")))
        if flat_valid:
            for stage in (0, 1):
                self._run(s.flat, _groups(w, h), [("uSrc", self.src)],
                          [("uFlat", self.flat), ("uCanvas", self.post_tmp)],
                          [("uPass", stage)], params=True)
            if flat_ground:
                self._copy(self.post_tmp, self.canvas)
        if not flat_ground and not use_temporal and block[0] > .5 and block[STYLE_INDEX["groundMode"]] > 0.5:
            self._copy(self.canvas, self.post_tmp)
            self._run(s.ground, _groups(w, h), [("uIn", self.post_tmp)],
                      [("uOut", self.canvas)], params=True)
        self.height.clear(format="FLOAT", value=(0.0, 0.0, 0.0, 0.0))

        plans = [plan_layer(w, h, r, (look.layer_specs[i][5]
                  if i < len(look.layer_specs) and look.layer_specs[i][5] == look.layer_specs[i][5]
                  else style.grid_factor), look.passes) for i, r in enumerate(radii)]
        pool_size = sum(p.passes * p.slots for p in plans)
        flat_only = block[0] > .5 and block[STYLE_INDEX["strokesOff"]] > .5
        use_pool = 0 < look.relax and not flat_only and pool_size <= MAX_STROKES
        if look.relax > 0 and not flat_only and not use_pool:
            raise ValueError("Relaxation exceeds the stroke budget; raise Brush size or lower resolution")
        if use_pool:
            self._copy(self.canvas, self.under)
        strokes = pool_size if use_pool else max(p.slots for p in plans)
        if strokes > MAX_STROKES:
            raise ValueError("Too many strokes for this size; raise Brush size")
        self._ensure_store(strokes)
        if flat_only:
            self._blur(self.src, self.ref, max(.1, radii[0] * .5))
            self._run(s.sobel, _groups(w, h), [("uRef", self.ref)], [("uOut", self.grad)], [size_px])

        regions = []
        next_slot = 0
        for layer, plan in enumerate(plans):
            if flat_only:
                break
            self._make_params(look, w, h, frame, layer)
            self._copy(self.canvas, self.snap)
            sigma = max(0.1, plan.radius * 0.5)
            if sigma != ref_sigma:
                self._blur(self.src, self.ref, sigma)
                ref_sigma = sigma
            self._run(s.sobel, _groups(w, h), [("uRef", self.ref)], [("uOut", self.grad)],
                      [size_px])
            if look.tensor_sigma > 0:
                self._run(s.features, _groups(w, h), [("uRef", self.ref), ("uTensor", self.tensor)],
                          [("uOut", self.field_tmp)], [("uPass", 1)], params=True)
                self._blur(self.field_tmp, self.tensor, look.tensor_sigma * scale)
                self._run(s.features, _groups(w, h), [("uRef", self.ref), ("uTensor", self.tensor)],
                          [("uOut", self.grad)], [("uPass", 2)], params=True)
            if look.etf > 0:
                self._etf(look.etf)
            if block[0] > 0.5 and (block[STYLE_INDEX["fieldMode"]] > 0 or
                                   block[STYLE_INDEX["minFieldMag"]] > 0):
                self._run(s.stylefield, _groups(w, h), [("uGrad", self.grad)],
                          [("uOut", self.field_tmp)], params=True)
                self._copy(self.field_tmp, self.grad)
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
            for step in range(look.relax * look.relax_subpasses):
                iteration, subpass = divmod(step, look.relax_subpasses)
                self._run(s.relax, (-(-next_slot // 64), 1, 1),
                          [("uSrc", self.src), ("uGround", self.under)],
                          [("uVerts", self._verts), ("uHeads", self._heads)],
                          [("uPool", (next_slot, subpass, look.relax_subpasses, 0))],
                          [("uRelax", (float(iteration), 0.0, 0.0, 0.0))], params=True)
                # A blended stroke cannot be taken back, so repaint the pool.
                self._copy(self.under, self.canvas)
                self.height.clear(format="FLOAT", value=(0.0, 0.0, 0.0, 0.0))
                for first, count, layer in regions:
                    self._make_params(look, w, h, frame, layer)
                    self._draw(first, count, layer)

        if look.impasto_light > 0.0:
            self._run(s.impasto, _groups(w, h), [("uHeight", self.height)],
                      [("uCanvas", self.canvas)], [size_px], params=True)

        self.output = self.canvas
        if block[0] > 0.5:
            color = self.canvas
            if block[STYLE_INDEX["licStrength"]] > 0 or block[STYLE_INDEX["watercolor"]] > 0:
                self._run(s.post, _groups(w, h), [("uColor", self.canvas), ("uGrad", self.grad),
                          ("uFlatS", self.flat), ("uToothS", self.tooth), ("uSrc", self.src)],
                          [("uOut", self.post_tmp)],
                          [("uPass", 1 if block[STYLE_INDEX["watercolor"]] > 0 else 0),
                           ("uFlatValid", int(flat_valid))], params=True)
                color = self.post_tmp
            self._copy(color, self.final)
            if block[STYLE_INDEX["finish"]] > 0:
                self._run(s.finish, _groups(w, h), [("uColor", color),
                          ("uHeight", self.height), ("uTooth", self.tooth)],
                          [("uOut", self.final)], params=True)
            self._run(s.post, _groups(w, h), [("uColor", self.canvas), ("uGrad", self.grad),
                      ("uFlatS", self.flat), ("uToothS", self.tooth), ("uSrc", self.src)],
                      [("uOut", self.final)], [("uPass", 2), ("uFlatValid", int(flat_valid))],
                      params=True)
            self.output = self.final
        self._have_prev = True
        self._prev_key = key
        return self.output

    def read_pixels(self):
        """The canvas as a float32 NumPy array (height, width, 4), bottom row
        first."""
        return read_texture_pixels(self.output)
