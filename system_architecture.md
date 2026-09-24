# Architecture

`src/` and `shaders/` contain an independent copy of the Paintify GPU renderer.
`tools/build.bat` builds it with the repository root compiled into `SBR_ROOT_DIR`,
which is used to locate shaders at runtime.

The Blender add-on registers `PAINTIFY_CompositorNode`, a custom compositor
group node. Each instance owns a distinct internal compositor node group with
an Image node linked to Group Output. The `paintify.paint_node` operator invokes
the external GPU renderer for the chosen image or video file and loads the
result into that internal Image node. Rendering and video decode/encode happen
in the GPU renderer process; the add-on is a Blender UI and compositor bridge.

Do not add an image input socket unless there is an implementation that actually
passes its pixels to the renderer. Python custom group nodes expose sockets but
cannot implement arbitrary compositor pixel operations.
