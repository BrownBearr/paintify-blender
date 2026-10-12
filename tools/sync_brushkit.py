#!/usr/bin/env python3
"""Refresh shared brush definitions and portable GLSL from a Brushkit checkout."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "blender_addon/paintify_gpu"


def portable(source):
    source = re.sub(r'^#version.*\n|^#include.*\n|^layout\(.*\) (?:uniform|in).*\n',
                    '', source, flags=re.M)
    source = re.sub(r'^uniform .*\n', '', source, flags=re.M)
    source = re.sub(r'\bthread\b', 'threadWidth', source)
    return source.encode('ascii', 'replace').decode('ascii')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "export"
        subprocess.run(["c++", "-std=c++17", "-I", str(checkout / "src"),
                        str(ROOT / "tools/export_brushkit.cpp"),
                        str(checkout / "src/styles.cpp"), "-o", str(exe)], check=True)
        data = json.loads(subprocess.check_output([str(exe)], text=True))
    header = (checkout / "src/style.h").read_text()
    header = re.sub(r'//[^\n]*', '', header)
    fields = []
    for declaration in re.findall(r'\bfloat\s+([^;]+);', header):
        if '[' in declaration:
            break
        fields.extend(part.strip().split('=')[0].strip() for part in declaration.split(','))
    assert len(fields) == 132
    data['fields'] = fields
    data['upstream'] = subprocess.check_output(
        ['git', '-C', str(checkout), 'rev-parse', 'origin/main'], text=True).strip()
    (ADDON / "brushkit_data.json").write_text(json.dumps(data, indent=2) + '\n')

    shader_dir = ADDON / "shaders"
    style = (checkout / "shaders/style.glsl").read_text()
    style = re.sub(r'layout\(std140, binding = 1\) uniform Style \{[\s\S]*?\};',
                   '#define bk brushkit.bk\n#define bkPal brushkit.bkPal\n'
                   '#define bkLayerA brushkit.bkLayerA\n#define bkLayerB brushkit.bkLayerB', style)
    aliases = '#define hashU hash_u\n#define rgb2hsv rgb_to_hsv\n#define hsv2rgb hsv_to_rgb\n'
    (shader_dir / "style.glsl").write_text(aliases + style)
    for name in ('support', 'stylefield', 'finish', 'post', 'flat', 'features'):
        stage = portable((checkout / 'shaders' / (name + '.comp')).read_text())
        if name == 'post':
            stage = stage.replace('float y = p.y / IMG_SIZE.y;',
                                   'float y = 1.0 - p.y / IMG_SIZE.y;')
            stage = stage.replace('vec2 dir = vec2(cos(th), sin(th));',
                                   'vec2 dir = vec2(cos(th), -sin(th));')
        elif name == 'stylefield':
            stage = stage.replace('clamp(q, ivec2(0), size - 1)',
                                   'clamp(ivec2(q.x, size.y - 1 - q.y), ivec2(0), size - 1)')
            stage = stage.replace('mag = g.z;', 'g.y = -g.y;\n    mag = g.z;')
            stage = stage.replace('vec2 p = vec2(px) + 0.5;',
                                   'vec2 p = vec2(float(px.x) + 0.5, IMG_SIZE.y - float(px.y) - 0.5);')
            stage = stage.replace('sin(ang) * M, -cos(ang) * M',
                                   'sin(ang) * M, cos(ang) * M')
        (shader_dir / (name + '.glsl')).write_text(
            stage)
    flow = portable((checkout / 'shaders/flow.comp').read_text())
    # Blender has no Python mipmap builder. The host binds the selected pyramid level.
    flow = flow.replace(', lod)', ', 0.0)')
    (shader_dir / 'flow.glsl').write_text(flow)
    canvas = portable((checkout / 'shaders/canvas.comp').read_text())
    canvas = canvas.replace('vec3 sampleCatmullRom(sampler2D tex, vec2 uv)',
                            'vec3 sampleCatmullRom(vec2 uv)')
    canvas = canvas.replace('texelFetch(tex, q, 0)', 'texelFetch(uPrevCanvas, q, 0)')
    canvas = canvas.replace('sampleCatmullRom(uPrevCanvas, uvp)', 'sampleCatmullRom(uvp)')
    (shader_dir / 'canvas.glsl').write_text(canvas)
    fragment = (checkout / 'shaders/stroke.frag').read_text()
    body = fragment[fragment.index('void brushkitBrushModel()'):fragment.index('void main()')]
    body = re.sub(r'\bvTexHash\b', 'uint(vTexHash + 0.5)', body)
    (shader_dir / 'procedural.glsl').write_text(body.rstrip() + '\n')
    print(f'Synced {len(data["brushes"])} brush families from {data["upstream"][:7]}')


if __name__ == '__main__':
    main()
