/* Helpers shared by every Paintify stage. Ported from shaders/common.glsl of
 * the standalone renderer; names follow PainterlyImageCreatorWeb's worker.js.
 *
 * Blender compiles this for OpenGL, Vulkan and Metal, so it sticks to the
 * portable subset: unsigned hash arithmetic, no global const arrays, no
 * sampler parameters and no packing intrinsics.
 *
 * Every texture here is in Blender's orientation: texel row 0 is the bottom
 * of the image. */

#define MAX_VERTS 33
#define STROKES_PER_ROW 128
#define DEG_TO_RAD 0.017453292519943295

/* One stroke occupies MAX_VERTS texels of the vertex store, (x, y, arc, 0),
 * and two texels of the header store: (r, g, b, opacity) and
 * (vertex count, brush variant, total length, radius). */
ivec2 vert_texel(int stroke, int i)
{
  return ivec2((stroke % STROKES_PER_ROW) * MAX_VERTS + i, stroke / STROKES_PER_ROW);
}

ivec2 head_texel(int stroke, int k)
{
  return ivec2((stroke % STROKES_PER_ROW) * 2 + k, stroke / STROKES_PER_ROW);
}

uint hash_u(uint x)
{
  x ^= x >> 16u;
  x *= 0x7feb352du;
  x ^= x >> 15u;
  x *= 0x846ca68bu;
  x ^= x >> 16u;
  return x;
}

float hash01(uint x)
{
  return float(hash_u(x) & 0x00ffffffu) / 16777216.0;
}

vec2 hash2(uint x)
{
  return vec2(hash01(x), hash01(x ^ 0x9e3779b9u));
}

/* brush-texture.js `brushHash`: the tile variant comes from the seed
 * position, never from a frame counter, or animation flickers. */
uint brush_hash(ivec2 p, int layer)
{
  uint h = uint(p.x) * 374761393u + uint(p.y) * 668265263u + uint(layer) * 2246822519u;
  h = (h ^ (h >> 13u)) * 1274126177u;
  return h ^ (h >> 16u);
}

vec3 rgb_to_hsv(vec3 c)
{
  vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
  vec4 p = mix(vec4(c.b, c.g, K.w, K.z), vec4(c.g, c.b, K.x, K.y), step(c.b, c.g));
  vec4 q = mix(vec4(p.x, p.y, p.w, c.r), vec4(c.r, p.y, p.z, p.x), step(p.x, c.r));
  float d = q.x - min(q.w, q.y);
  return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + 1e-10)), d / (q.x + 1e-10), q.x);
}

vec3 hsv_to_rgb(vec3 c)
{
  vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
  vec3 p = abs(fract(vec3(c.x) + K.xyz) * 6.0 - vec3(K.w));
  return c.z * mix(vec3(K.x), clamp(p - vec3(K.x), 0.0, 1.0), c.y);
}

/* sRGB 0..1 -> Lab encoded like OpenCV uint8 (L*255/100, a+128, b+128). The
 * threshold slider is calibrated on this scale. */
vec3 rgb_to_lab(vec3 c)
{
  vec3 lin = mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
  float X = dot(lin, vec3(0.4124564, 0.3575761, 0.1804375)) / 0.95047;
  float Y = dot(lin, vec3(0.2126729, 0.7151522, 0.0721750));
  float Z = dot(lin, vec3(0.0193339, 0.1191920, 0.9503041)) / 1.08883;
  vec3 t = vec3(X, Y, Z);
  vec3 f = mix(7.787 * t + 16.0 / 116.0, pow(max(t, vec3(1e-8)), vec3(1.0 / 3.0)),
               step(vec3(0.008856), t));
  return vec3((116.0 * f.y - 16.0) * 2.55, 500.0 * (f.x - f.y) + 128.0,
              200.0 * (f.y - f.z) + 128.0);
}
