"""Compiles every Paintify stage with glslangValidator, twice: as strict Vulkan
GLSL, and as desktop OpenGL 4.3, the oldest OpenGL Blender runs on (the usual
Windows backend).

Blender builds these shaders for Metal, Vulkan and OpenGL from the same
source; a strict compiler catches the implicit conversions and newer-GLSL
constructs that one lenient driver would accept. Also rejects non-ASCII
bytes, which some Windows OpenGL drivers refuse even inside comments. The
compile tests skip when glslangValidator is not installed (Homebrew/apt
package: glslang).
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
VULKAN, OPENGL = "vulkan", "opengl"
_VERSION = {VULKAN: "#version 450\n", OPENGL: "#version 430 core\n"}


def _binding(target, index):
    return f"set = 0, binding = {index}" if target == VULKAN else f"binding = {index}"


def _push_constants(target, push):
    if not push:
        return ""
    if target == OPENGL:
        return "".join(f"uniform {_TYPES[kind]} {name};\n" for kind, name in push)
    members = "".join(f"  {_TYPES[kind]} {name};\n" for kind, name in push)
    defines = "".join(f"#define {name} pc.{name}\n" for _kind, name in push)
    return f"layout(push_constant) uniform PushConstants {{\n{members}}} pc;\n{defines}"


def _params_block(target, uses_params):
    if not uses_params:
        return ""
    return (stages.PARAMS_STRUCT + f"layout(std140, {_binding(target, 0)}) "
            "uniform ParamsBlock { PaintParams params; };\n")


def _samplers(target, names):
    return "".join(f"layout({_binding(target, i)}) uniform sampler2D {n};\n"
                   for i, n in enumerate(names))


def compute_glsl(name, target=VULKAN):
    _file, samplers, images, push, uses_params, group = stages.COMPUTE[name]
    out = [_VERSION[target],
           "layout(local_size_x = %d, local_size_y = %d, local_size_z = %d) in;\n" % group,
           _params_block(target, uses_params), _samplers(target, samplers)]
    for i, (fmt, image, access) in enumerate(images):
        qualifier = "" if "READ" in access else "writeonly "
        out.append(f"layout({_binding(target, i)}, {fmt.lower()}) uniform "
                   f"{qualifier}image2D {image};\n")
    out.append(_push_constants(target, push))
    out.append(stages.compute_source(name))
    return "".join(out)


def stroke_glsl(target=VULKAN):
    spec = stages.STROKE
    header = [_VERSION[target], _params_block(target, True),
              _samplers(target, spec["samplers"]), _push_constants(target, spec["push"])]
    varyings = ([("", k, n) for k, n in spec["smooth"]] +
                [("flat ", k, n) for k, n in spec["flat"]])
    vertex, fragment = stages.stroke_sources()
    vert = list(header)
    if target == VULKAN:
        vert.append("#define gl_InstanceID gl_InstanceIndex\n")
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


class ShaderSourceTests(unittest.TestCase):
    def test_sources_are_ascii(self):
        for path in sorted(stages.SHADER_DIR.glob("*.glsl")):
            with self.subTest(shader=path.name):
                path.read_bytes().decode("ascii")


@unittest.skipUnless(GLSLANG, "glslangValidator not installed")
class ShaderCompileTests(unittest.TestCase):
    def compile(self, stage, text, target):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"shader.{stage}"
            path.write_text(text, encoding="utf-8")
            if target == VULKAN:
                args = ["-V", "--target-env", "vulkan1.2", "-o", str(Path(tmp) / "out.spv")]
            else:
                args = []  # Plain validation against the #version 430 core profile.
            result = subprocess.run([GLSLANG, *args, str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_compute_stages(self):
        for target in (VULKAN, OPENGL):
            for name in stages.COMPUTE:
                with self.subTest(target=target, stage=name):
                    self.compile("comp", compute_glsl(name, target), target)

    def test_stroke_stages(self):
        for target in (VULKAN, OPENGL):
            vertex, fragment = stroke_glsl(target)
            with self.subTest(target=target):
                self.compile("vert", vertex, target)
                self.compile("frag", fragment, target)


if __name__ == "__main__":
    unittest.main()
