# Paintify Live architecture

The add-on is a 3D Viewport draw handler and sidebar panel. `GPUOffScreen` draws
the current viewport at the selected resolution. The add-on reads RGBA8 pixels,
flips row order, and sends a binary `PPV1` frame to `paintify-stream.exe` via
stdin. A worker thread handles all pipe I/O and allows only one frame in flight.
Blender GPU calls remain on the main thread. The latest painted frame comes
back over stdout, is uploaded as `GPUTexture`, and is drawn with `IMAGE_COLOR`
over the active viewport. A timer schedules repaint at the selected cadence.
Blender 5.2 requires `FLOAT` buffers when constructing a `GPUTexture`, even
when the texture format is `RGBA8`; NumPy normalizes the returned bytes first.

`paintify-stream.exe` owns a persistent hidden GLFW OpenGL context and a
`Pipeline`. It uses the original GPU renderer stages in `src/pipeline.cpp` and
`shaders/`. A fixed 48-byte little-endian header contains frame dimensions,
sequence and look controls, followed by top-row-first RGBA8. The reply is a
16-byte header and top-row-first RGBA8. The process is restarted only when the
overlay is toggled, not per frame. Preset or parameter changes reset temporal
reuse; otherwise the previous paint may carry forward for stable strokes.

The preview is an overlay, not a compositor output or render pass. Python GPU
buffer readback is the main likely performance bottleneck. The default 50%
capture resolution is an intentional throughput tradeoff.
