# Live viewport rewrite

- [NEW] `src/stream.cpp`: persistent raw RGBA GPU renderer process.
- [MODIFY] `CMakeLists.txt`: build the stream renderer beside the existing CLI.
- [REPLACE] `blender_addon/paintify_gpu/__init__.py`: 3D Viewport overlay and controls.
- [REPLACE] `blender_addon/paintify_gpu/engine.py` with `stream_bridge.py`: asynchronous frame transport.
- [MODIFY] `README.md`, `system_architecture.md`, `task.md`: explain live viewport behavior and limits.
- [REPLACE] bridge tests: protocol framing, validation, row orientation.

Verify the Python tests, C++ build, real frame stream through the GPU backend,
and Blender registration if an executable is available.
