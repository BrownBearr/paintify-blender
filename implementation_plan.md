# Blender GPU module port and painted renders

- [NEW] `blender_addon/paintify_gpu/painter.py`, `stages.py`, `shaders/`: the
  Hertzmann pipeline on Blender's `gpu` module, so macOS (Metal) works.
- [NEW] `looks.py`, `brushes.py`: styles, frame-relative brush scale, brush tiles.
- [NEW] `render.py`: painted still and animation operators.
- [SPLIT] `__init__.py` into `settings.py`, `viewport.py`, `ui.py`.
- [REMOVE] `stream_bridge.py`, `src/stream.cpp`: the external renderer process.
- [REPLACE] tests: pure Python, glslang shader compile, Blender smoke test.

Verify the Python tests, strict shader compiles, and the smoke test in
Blender 5.2 (overlay, still, PNG sequence, MP4).
