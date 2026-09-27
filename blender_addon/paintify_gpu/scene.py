"""Paintify Scene: brush strokes that belong to objects instead of the screen.

The screen painter repaints the image each frame, so its strokes swim over a
turning object. Here a stroke painted on an object is lifted onto its surface
and redrawn from there on every later frame:

1. A G-buffer pass draws the scene's geometry with the painted camera:
   object-space position and object slot per pixel, plus linear view depth.
2. The background (world, and instanced geometry) is painted by the screen
   pipeline, masked so it seeds no stroke on an object. Blurs and gradients
   in scene mode stay within one G-buffer slot, so every surface is painted
   from its own appearance, not from whatever passes in front of it.
3. Per layer, coarse to fine: the stored strokes of the layer are projected
   through their object's current matrices and drawn, hidden where the
   G-buffer holds a nearer surface. Then the Hertzmann tracer paints only
   where object surface is still uncovered (first view, or surface that just
   turned into view). Those new strokes are cut at silhouettes, lifted
   through the G-buffer into object space (or world space) and appended to
   the layer's store by a GPU prefix sum, since Blender's Python GPU API has
   no atomics.

Covered surface never seeds again, so the stores grow only as new surface
comes into view. Strokes keep their brush texture and their colour jitter; by
default their colour follows the current frame, so shading stays right while
the paint stays put. Deforming meshes are not followed: an anchor is a point
in the object's space, which suits rigid motion.

One stroke store per Painter, so the viewport and each render job build their
own.
"""

import bpy
import gpu
import numpy as np
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix

from .looks import draw_order_step, plan_layer
from .painter import MAX_STROKES, MAX_VERTS, STROKES_PER_ROW, Painter, _groups, shaders

SPACES = (
    ("SCREEN", "Screen", "Paint the image every frame. Strokes are redrawn as objects and "
                         "the camera move"),
    ("OBJECT", "Object", "Strokes stick to the surface of each object and move with it"),
    ("WORLD", "World", "Strokes stick to world positions: they stay put as the camera moves "
                       "and moving objects slide under them"),
)

SCENE_HEADS = 4
SCAN_BLOCK = 64
TABLE_TEXELS = 8
MAX_SLOTS = 4096
MAX_LAYERS = 8
MAX_SCENE_ROWS = 2048  # 262144 strokes per layer
FIRST_ROWS = 32
SETTLE_PASSES = 2
SLOT_NONE = -1.0  # background
SLOT_OCCLUDER = -2.0  # hides strokes behind it, but gets screen strokes
FAR = 1e30
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}

# --- geometry ----------------------------------------------------------------

_batches = {}


@persistent
def _geometry_changed(_scene, depsgraph):
    if any(update.is_updated_geometry for update in depsgraph.updates):
        _batches.clear()


@persistent
def _file_loaded(*_args):
    _batches.clear()


def register():
    bpy.app.handlers.depsgraph_update_post.append(_geometry_changed)
    bpy.app.handlers.load_post.append(_file_loaded)


def unregister():
    for handlers, fn in ((bpy.app.handlers.depsgraph_update_post, _geometry_changed),
                         (bpy.app.handlers.load_post, _file_loaded)):
        if fn in handlers:
            handlers.remove(fn)
    _batches.clear()


def _changes_per_frame(original):
    """True when the object's evaluated geometry may differ between frames."""
    if len(getattr(original, "modifiers", ())):
        return True
    data = original.data
    return getattr(data, "shape_keys", None) is not None


def _batch(obj, frame):
    """G-buffer batch of an evaluated object's triangles, cached until its
    geometry changes. Needs an active GPU context."""
    original = obj.original
    key = (obj.name_full, obj.data.name_full if obj.data else "",
           frame if _changes_per_frame(original) else None)
    batch = _batches.get(key)
    if batch is None and key not in _batches:
        mesh = obj.to_mesh()
        try:
            mesh.calc_loop_triangles()
            co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get("co", co)
            tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            mesh.loop_triangles.foreach_get("vertices", tris)
        finally:
            obj.to_mesh_clear()
        if len(tris):
            batch = batch_for_shader(shaders().gbuffer, "TRIS", {"pos": co.reshape(-1, 3)},
                                     indices=tris.reshape(-1, 3))
        _batches[key] = batch
    return batch


class SceneView:
    """The camera and geometry of one painted frame."""

    def __init__(self, view, projection, anchor="OBJECT", relight=True, items=()):
        self.view = view.copy()
        self.projection = projection.copy()
        self.anchor = anchor
        self.relight = relight
        self.items = list(items)  # (object key or None for instances, matrix, batch)


def collect(depsgraph, view, projection, anchor, relight, render=False):
    """A SceneView of every visible object with geometry. Instances only
    hide what is behind them: they have no stable identity to anchor to.
    Needs an active GPU context."""
    frame = depsgraph.scene.frame_current
    items = []
    for inst in depsgraph.object_instances:
        obj = inst.object
        if obj.type not in GEOMETRY_TYPES:
            continue
        original = obj.original
        if render and original.hide_render:
            continue
        batch = _batch(obj, frame)
        if batch is None:
            continue
        key = None if inst.is_instance else original.name_full
        items.append((key, inst.matrix_world.copy(), batch))
    return SceneView(view, projection, anchor, relight, items)


# --- the painter -------------------------------------------------------------

class _Store:
    """One layer's strokes in object or world space."""

    def __init__(self, rows):
        self.rows = rows
        self.anchors = gpu.types.GPUTexture((STROKES_PER_ROW * MAX_VERTS, rows), format="RGBA32F")
        self.heads = gpu.types.GPUTexture((STROKES_PER_ROW * SCENE_HEADS, rows), format="RGBA32F")

    @property
    def capacity(self):
        return self.rows * STROKES_PER_ROW


def _rows(count):
    return max(1, -(-count // STROKES_PER_ROW))


def _rows_of(matrix):
    return [tuple(matrix[r]) for r in range(4)]


class ScenePainter(Painter):
    """A Painter that, given a SceneView, keeps object strokes on their
    surfaces from frame to frame. Without one it paints the screen."""

    def __init__(self):
        super().__init__()
        self._slots = {}
        self._table = None
        self._gbuffer_key = None
        self._gbuffer_fb = None
        self._scene_fb_key = None
        self._scene_fb = None
        self._shadow = None
        self.gpos = None
        self.gdepth = None
        self.reset_scene()

    def reset_scene(self):
        """Drop every stored stroke; the next frame paints objects afresh."""
        self._stores = []
        self._counts = []
        self._counter = None
        self._scene_key = None
        self.scene_strokes = 0
        self.scene_full = False

    # --- G-buffer -----------------------------------------------------------

    def _slot(self, key):
        if key is None:
            return SLOT_OCCLUDER
        slot = self._slots.get(key)
        if slot is None:
            if len(self._slots) + 1 >= MAX_SLOTS:
                return SLOT_OCCLUDER
            slot = self._slots[key] = len(self._slots) + 1
        return float(slot)

    def _render_gbuffer(self, view, width, height):
        size = (width, height)
        self.gpos = self._texture("gpos", size, "RGBA32F")
        self.gdepth = self._texture("gdepth", size, "R32F")
        zbuf = self._texture("gz", size, "DEPTH_COMPONENT32F")
        if self._gbuffer_key != size:
            self._gbuffer_fb = gpu.types.GPUFrameBuffer(depth_slot=zbuf,
                                                        color_slots=(self.gpos, self.gdepth))
            self._gbuffer_key = size
        self.gpos.clear(format="FLOAT", value=(0.0, 0.0, 0.0, SLOT_NONE))
        self.gdepth.clear(format="FLOAT", value=(FAR, 0.0, 0.0, 0.0))

        rows = {0: (view.projection @ view.view, view.view, Matrix.Identity(4))}
        shader = shaders().gbuffer
        fb = self._gbuffer_fb
        with fb.bind():
            fb.viewport_set(0, 0, width, height)
            fb.clear(depth=1.0)
            blend = gpu.state.blend_get()
            depth_test = gpu.state.depth_test_get()
            depth_mask = gpu.state.depth_mask_get()
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set("LESS_EQUAL")
            gpu.state.depth_mask_set(True)
            gpu.state.face_culling_set("NONE")
            shader.bind()
            for key, matrix, batch in view.items:
                slot = self._slot(key)
                model_view = view.view @ matrix
                shader.uniform_float("uMVP", view.projection @ model_view)
                shader.uniform_float("uViewZ", tuple(model_view[2]))
                shader.uniform_float("uSlot", (slot, 0.0, 0.0, 0.0))
                batch.draw(shader)
                if slot > 0:
                    rows[int(slot)] = (view.projection @ model_view, model_view, matrix)
            gpu.state.depth_mask_set(depth_mask)
            gpu.state.depth_test_set(depth_test)
            gpu.state.blend_set(blend)

        # Every slot ever handed out gets a row; absent objects stay zero.
        table = np.zeros((len(self._slots) + 1, TABLE_TEXELS, 4), dtype=np.float32)
        for slot, (mvp, model_view, model) in rows.items():
            table[slot, 0:4] = _rows_of(mvp)
            table[slot, 4] = tuple(model_view[2])
            table[slot, 5:8] = _rows_of(model)[:3]
        buf = gpu.types.Buffer("FLOAT", table.size, table.ravel())
        self._table = gpu.types.GPUTexture((TABLE_TEXELS, table.shape[0]), format="RGBA32F",
                                           data=buf)

        p = view.projection
        perspective = abs(p[3][3]) < 1e-6
        self._view_consts = (p[1][1] * height * 0.5, 1.0 if perspective else 0.0, 0.0, 0.0)

    # --- stroke stores ------------------------------------------------------

    def _ensure_capacity(self, layer, needed):
        """Grows a layer's store to hold `needed` strokes, keeping its strokes."""
        rows = min(MAX_SCENE_ROWS, _rows(needed))
        old = self._stores[layer]
        if old is not None and old.rows >= rows:
            return
        if old is not None:
            rows = min(MAX_SCENE_ROWS, max(rows, old.rows * 3 // 2))
        store = _Store(max(rows, FIRST_ROWS))
        if old is not None:
            copy = shaders().copy32
            for src, dst in ((old.anchors, store.anchors), (old.heads, store.heads)):
                self._run(copy, _groups(src.width, src.height), [("uIn", src)], [("uOut", dst)],
                          [("uSize", (src.width, src.height))])
        self._stores[layer] = store

    def _start_scene(self, look, anchor, layers):
        key = (look, anchor)
        if self._scene_key != key or len(self._stores) != layers:
            self.reset_scene()
            self._scene_key = key
            self._stores = [None] * layers
            self._counts = [0] * layers
            self._counter = gpu.types.GPUTexture((MAX_LAYERS, 1), format="RGBA32F")
            self._counter.clear(format="FLOAT", value=(0.0, 0.0, 0.0, 0.0))

    # --- the frame ----------------------------------------------------------

    def paint(self, source, width, height, look, scale=1.0, temporal=True, frame=0, view=None):
        """Painter.paint, plus object strokes when `view` (a SceneView) is
        given. Returns the painted texture, valid until the next paint."""
        if view is None or view.anchor == "SCREEN":
            return super().paint(source, width, height, look, scale, temporal, frame)
        if len(look.style.radii) > MAX_LAYERS:
            raise ValueError("Too many layers for Paintify Scene")
        shaders()
        self._render_gbuffer(view, width, height)
        super().paint(source, width, height, look, scale, temporal, frame,
                      mask=self.gpos, impasto=False)
        self._shadow_mask()
        # A fresh store settles over a few frames, as strokes near silhouettes
        # find their place; do that before showing the first one.
        passes = 1 + (SETTLE_PASSES if self._scene_key != (look, view.anchor) else 0)
        for _ in range(passes):
            canvas = self._paint_objects(look, view)
        return canvas

    def _shadow_mask(self):
        """Surface within spill reach of a nearer one (shadow.glsl)."""
        w, h = self.size
        near = self._texture("scene_near", (w, h), "R32F")
        self._shadow = self._texture("scene_shadow", (w, h), "R32F")
        reach = max(1, min(64, int(self._radii[0] * 1.5 + 0.5)))
        for mode, src, dst in ((0, self.gdepth, near), (1, near, self._shadow)):
            self._run(shaders().shadow, _groups(w, h), [("uGDepth", self.gdepth), ("uIn", src)],
                      [("uOut", dst)], [("uShadow", (mode, reach, 0, 0))], params=True)

    def _draw_stored(self, layer, framebuffer, relight):
        count = self._counts[layer]
        if count <= 0:
            return
        s = shaders()
        store = self._stores[layer]
        self._stroke_pass(framebuffer, s.scene_stroke, s.scene_strip, count,
                          [("uAnchors", store.anchors), ("uSHeads", store.heads),
                           ("uBrush", self._atlas), ("uRef", self.ref), ("uGDepth", self.gdepth),
                           ("uTable", self._table), ("uErr", self.err), ("uShadow", self._shadow)],
                          [("uDraw", (0, count, int(relight), int(layer > 0)))],
                          [("uTex", self._layer_tex(layer)), ("uView", self._view_consts)])

    def _paint_objects(self, look, view):
        s = shaders()
        w, h = self.size
        size = (w, h)
        size_px = ("uSize", size)
        plans = [plan_layer(w, h, r, look.style.grid_factor) for r in self._radii]
        self._start_scene(look, view.anchor, len(plans))

        canvas = self._texture("scene_canvas", size, "RGBA16F")
        cover = self._texture("scene_cover", size, "RGBA16F")
        if self._scene_fb_key != size:
            self._scene_fb = gpu.types.GPUFrameBuffer(color_slots=(canvas, cover))
            self._scene_fb_key = size
        fb = self._scene_fb
        # Impasto height of the background strokes, no coverage yet.
        self._copy(self.height, cover, mode=4)

        pool = max(p.passes * p.slots for p in plans)
        if pool > MAX_STROKES:
            raise ValueError("Too many strokes for this size; raise Brush size")
        self._ensure_store(pool)
        flags = self._texture("scene_flags", (STROKES_PER_ROW, _rows(pool)), "R32F")
        blocks = self._texture("scene_blocks",
                               (STROKES_PER_ROW, _rows(-(-pool // SCAN_BLOCK))), "RGBA32F")
        world = int(view.anchor == "WORLD")

        for layer, plan in enumerate(plans):
            self._blur(self.src, self.ref, max(0.1, plan.radius * 0.5), self.gpos)
            if layer == 0:
                self._run(s.select, _groups(w, h),
                          [("uA", self.canvas), ("uB", self.ref), ("uGPos", self.gpos)],
                          [("uOut", canvas)], [size_px])
            else:
                # Coverage is per layer: a fine layer seeds under coarse paint.
                self._copy(cover, self.tmp, mode=4)
                self._copy(self.tmp, cover)
            self._sobel(self.gpos)
            new = plan.passes * plan.slots
            self._ensure_capacity(layer, self._counts[layer] + new)
            if layer > 0 and self._counts[layer]:
                # What the coarser paint still misses decides which stored
                # detail strokes this view keeps.
                self._run(s.errmap, _groups(w, h), [("uA", self.ref), ("uB", canvas)],
                          [("uOut", self.err)], [("uMode", 0), size_px])
            self._draw_stored(layer, fb, view.relight)

            self._run(s.errmap, _groups(w, h), [("uA", self.ref), ("uB", canvas)],
                      [("uOut", self.err)], [("uMode", 0), size_px])
            cells = self._texture(("cells", layer), (plan.cells_x, plan.cells_y), "RGBA32F")
            self._run(s.scene_cells, _groups(plan.cells_x, plan.cells_y),
                      [("uErr", self.err), ("uCover", cover), ("uGPos", self.gpos)],
                      [("uOut", cells)],
                      [("uGrid", (plan.grid, int(layer == 0), plan.cells_x, plan.cells_y)),
                       size_px])
            step = draw_order_step(plan.slots)
            for pass_index in range(plan.passes):
                first = pass_index * plan.slots
                self._trace(cells, plan, layer, pass_index, first, canvas, False)
                self._run(s.lift_count, (-(-plan.slots // 64), 1, 1),
                          [("uVerts", self._verts), ("uGPos", self.gpos), ("uGDepth", self.gdepth),
                           ("uShadow", self._shadow)],
                          [("uHeads", self._heads), ("uFlags", flags)],
                          [("uRange", (first, plan.slots, step, 0))], params=True)
                self._draw(first, plan.slots, layer, framebuffer=fb)

            store = self._stores[layer]
            scan = (new, layer, store.capacity)
            blocks_n = -(-new // SCAN_BLOCK)
            self._run(s.scan, (-(-blocks_n // 64), 1, 1), [("uFlags", flags)],
                      [("uBlocks", blocks), ("uCounter", self._counter)],
                      [("uScan", (0, *scan))])
            self._run(s.scan, (1, 1, 1), [("uFlags", flags)],
                      [("uBlocks", blocks), ("uCounter", self._counter)],
                      [("uScan", (1, *scan))])
            self._run(s.lift_write, (-(-new // 64), 1, 1),
                      [("uVerts", self._verts), ("uHeads", self._heads), ("uFlags", flags),
                       ("uBlocks", blocks), ("uCounter", self._counter), ("uGPos", self.gpos),
                       ("uGDepth", self.gdepth), ("uRef", self.ref), ("uTable", self._table)],
                      [("uAnchors", store.anchors), ("uSHeads", store.heads)],
                      [("uRange", (new, layer, store.capacity, world)),
                       ("uOrder", (plan.slots, step, 0, 0))],
                      [("uView", self._view_consts)], params=True)

        # One small readback per frame: next frame's instance counts.
        counter = np.array(self._counter.read(), dtype=np.float32)[0]
        self._counts = [int(counter[layer, 0]) for layer in range(len(plans))]
        self.scene_strokes = sum(self._counts)
        self.scene_full = any(counter[layer, 2] > counter[layer, 0] for layer in range(len(plans)))

        if look.impasto_light > 0.0:
            self._impasto(canvas, cover)
        self.output = canvas
        return canvas
