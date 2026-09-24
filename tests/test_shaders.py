"""Compiles every Paintify stage as strict Vulkan GLSL with glslangValidator.

Blender builds these shaders for Metal, Vulkan and OpenGL from the same
source; a strict compiler catches the implicit conversions and GL-only
constructs that one lenient driver would accept. Skipped when
glslangValidator is not installed (Homebrew/apt package: glslang).
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blender_addon" / "paintify_gpu"))
import stages

GLSLANG = shutil.which("glslangValidator")
_TYPES = {"INT": "int", "FLOAT": "float", "IVEC2": "ivec2", "IVEC4": "ivec4",
          "VEC3": "vec3", "VEC4": "vec4"}


def _push_block(push):
    if not push:
        return ""
    members = "".join(f"  {_TYPES[kind]} {name};\n" for kind, name in push)
    defines = "".join(f"#define {name} pc.{name}\n" for _kind, name in push)
    return f"layout(push_constant) uniform PushConstants {{\n{members}}} pc;\n{defines}"


def _params_block(uses_params):
    if not uses_params:
        return ""
    return (stages.PARAMS_STRUCT +
            "layout(std140, set = 0, binding = 0) uniform ParamsBlock { PaintParams params; };\n")


def _samplers(names):
    return "".join(f"layout(set = 0, binding = {1 + i}) uniform sampler2D {n};\n"
                   for i, n in enumerate(names))


def compute_glsl(name):
    _file, samplers, images, push, uses_params, group = stages.COMPUTE[name]
    out = ["#version 450\n",
           "layout(local_size_x = %d, local_size_y = %d, local_size_z = %d) in;\n" % group,
           _params_block(uses_params), _samplers(samplers)]
    for i, (fmt, image, access) in enumerate(images):
        qualifier = "" if "READ" in access else "writeonly "
        out.append(f"layout(set = 0, binding = {20 + i}, {fmt.lower()}) uniform "
                   f"{qualifier}image2D {image};\n")
    out.append(_push_block(push))
    out.append(stages.compute_source(name))
    return "".join(out)


def stroke_glsl():
    spec = stages.STROKE
    header = ["#version 450\n", _params_block(True), _samplers(spec["samplers"]),
              _push_block(spec["push"])]
    varyings = ([("", k, n) for k, n in spec["smooth"]] +
                [("flat ", k, n) for k, n in spec["flat"]])
    vertex, fragment = stages.stroke_sources()
    vert = header + ["#define gl_InstanceID gl_InstanceIndex\n"]
    vert += [f"layout(location = {i}) in {_TYPES[k]} {n};\n"
             for i, (k, n) in enumerate(spec["vertex_in"])]
    vert += [f"layout(location = {i}) {q}out {_TYPES[k]} {n};\n"
             for i, (q, k, n) in enumerate(varyings)]
    frag = list(header)
    frag += [f"layout(location = {i}) {q}in {_TYPES[k]} {n};\n"
             for i, (q, k, n) in enumerate(varyings)]
    frag += [f"layout(location = {i}) out {_TYPES[k]} {n};\n"
             for i, (k, n) in enumerate(spec["fragment_out"])]
    return "".join(vert) + vertex, "".join(frag) + fragment


@unittest.skipUnless(GLSLANG, "glslangValidator not installed")
class ShaderCompileTests(unittest.TestCase):
    def compile(self, stage, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"shader.{stage}"
            path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [GLSLANG, "-V", "--target-env", "vulkan1.2", "-o", str(Path(tmp) / "out.spv"),
                 str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_compute_stages(self):
        for name in stages.COMPUTE:
            with self.subTest(stage=name):
                self.compile("comp", compute_glsl(name))

    def test_stroke_stages(self):
        vertex, fragment = stroke_glsl()
        self.compile("vert", vertex)
        self.compile("frag", fragment)


if __name__ == "__main__":
    unittest.main()
