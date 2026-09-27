# Paintify Live architecture

The add-on paints on Blender's `gpu` module. `painter.py` owns the render
targets and runs the stages; `stages.py` declares each shader's resources and
`shaders/*.glsl` holds the code, ported from the paintify-GPU renderer
(`src/pipeline.cpp` and `shaders/` in that repository). Blender compiles the
GLSL for Metal, Vulkan or OpenGL, so the same code runs on macOS, Windows and
Linux.

Per painted frame, all on the GPU with no readback:

1. Import the source texture, keeping the previous one for temporal mode.
2. Underpaint: the previous canvas (temporal), the coarsest Gaussian, or the
   image mean.
3. Per layer, coarse to fine: Gaussian reference, Sobel gradient, Lab error
   against the canvas, per-cell reduction. Then 8 to 32 passes of seed+trace
   (compute) and stroke rasterisation (instanced triangle strips, premultiplied
   blend into canvas and height targets).
4. Optional relaxation over the frame's stroke pool, repainting after each
   iteration, then impasto lighting.

Blender's Python GPU API has no storage buffers or atomics, so strokes live in
RGBA32F textures and each pass owns one cell of every block of `passes`
consecutive cells, picked by a hashed permutation. That replaces the atomic
seed compaction of the paintify-GPU renderer and makes painting deterministic.
Per-layer values travel as push constants; frame settings sit in a uniform
buffer created once per frame.

Brush radii scale with `sqrt(width * height)` (`looks.stroke_scale`), so the
look depends on the frame, not the pixel count.

`viewport.py` draws the live overlay from a 3D Viewport `POST_PIXEL` handler.
In camera view it renders the camera frame through `GPUOffScreen.draw_view3d`
with the camera's matrices at the render aspect; otherwise the whole region.
The painted canvas is drawn back as a textured quad.

`scene.py` is Paintify Scene: `ScenePainter` extends `Painter` so strokes on
objects persist in object (or world) space instead of being repainted each
frame. Per painted frame:

1. A G-buffer pass draws every visible object's evaluated triangles with the
   painted camera: object-space position and a stable per-object slot
   (RGBA32F) and linear view depth (R32F). A small table texture holds each
   slot's current model-view-projection, view-z row and model matrix.
2. The screen pipeline paints the background with cells masked off objects.
   Blurs and Sobel stay within one slot, so no surface is painted from the
   colours of whatever passes in front of it.
3. Per layer: the stored strokes are projected through their slot's matrices
   and drawn (`scene_stroke_vert.glsl` + the shared fragment stage), hidden
   per fragment behind nearer G-buffer depth, faded when foreshortening
   squashes or stretches them, and, below the coarsest layer, retired where
   the coarser paint no longer misses detail. Their lengths stay in the
   pixels they were painted in, so coverage and brush texture ride with them.
4. `scene_cells.glsl` seeds only where object surface has no stroke of this
   layer yet (coverage accumulates in the green channel of the height
   target). The ordinary tracer paints there; `lift_count.glsl` cuts each new
   stroke at silhouettes and flags it; `scan.glsl` prefix-sums the flags and
   `lift_write.glsl` appends the flagged strokes, in draw order, to the
   layer's store through the G-buffer (bilinear, so the redraw lands to a
   fraction of a pixel). Strokes seeded within spill reach of a nearer
   surface (`shadow.glsl`) are drawn but not stored.

Blender's Python GPU API has no atomics, so compaction is a two-level scan
with one serial pass over block sums; the store count comes back to the CPU
in one 1-texel-per-layer readback per frame, which sizes the next frame's
instanced draw. A fresh store runs the object pass three times on its first
frame so the first shown frame is already the settled one.

`render.py` renders each frame with the scene's engine, saves the result
through the scene's colour management (the display-referred image the
overlay also paints), paints it at render size and writes the scene's output.
A scratch scene with the Standard view transform writes the pixels unchanged;
movies are encoded by that scene's sequencer from a temporary PNG sequence.
The render uses its own Painter, so its temporal state never mixes with the
viewport's.
