# Paintify Live architecture

The add-on paints on Blender's `gpu` module. `painter.py` owns the render
targets and runs the stages; `stages.py` declares each shader's resources and
`shaders/*.glsl` holds the code, ported from the standalone renderer
(`src/pipeline.cpp`, `shaders/`). Blender compiles the GLSL for Metal, Vulkan
or OpenGL, so the same code runs on macOS, Windows and Linux.

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
seed compaction of the standalone renderer and makes painting deterministic.
Per-layer values travel as push constants; frame settings sit in a uniform
buffer created once per frame.

Brush radii scale with `sqrt(width * height)` (`looks.stroke_scale`), so the
look depends on the frame, not the pixel count.

`viewport.py` draws the live overlay from a 3D Viewport `POST_PIXEL` handler.
In camera view it renders the camera frame through `GPUOffScreen.draw_view3d`
with the camera's matrices at the render aspect; otherwise the whole region.
The painted canvas is drawn back as a textured quad.

`render.py` renders each frame with the scene's engine, saves the result
through the scene's colour management (the display-referred image the
overlay also paints), paints it at render size and writes the scene's output.
A scratch scene with the Standard view transform writes the pixels unchanged;
movies are encoded by that scene's sequencer from a temporary PNG sequence.
The render uses its own Painter, so its temporal state never mixes with the
viewport's.
