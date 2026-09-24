/* One triangle-strip instance per stroke, two vertices per polyline point,
 * so a fragment is covered once per stroke like worker.js's unioned mask.
 * Points past the stroke's length collapse onto the last one.
 *
 * uDraw: (first slot, slot count, order step, unused). Instance i draws slot
 * (i * step) % count; step is coprime to count, so every slot is drawn once
 * in an order decorrelated from position. */

float taper_at(float u, float amt)
{
  if (amt <= 0.0) {
    return 1.0;
  }
  float end_frac = 0.06 + 0.30 * amt;
  float e = min(u, 1.0 - u);
  float s = clamp(e / end_frac, 0.0, 1.0);
  s = s * s * (3.0 - 2.0 * s);
  return (1.0 - 0.45 * amt) + 0.45 * amt * s;
}

vec2 point_at(int stroke, int i)
{
  return texelFetch(uVerts, vert_texel(stroke, i), 0).xy;
}

void main()
{
  uint count = uint(max(uDraw.y, 1));
  int stroke = uDraw.x + int((uint(gl_InstanceID) * uint(uDraw.z)) % count);
  vec4 h0 = texelFetch(uHeads, head_texel(stroke, 0), 0);
  vec4 h1 = texelFetch(uHeads, head_texel(stroke, 1), 0);
  int vc = int(h1.x + 0.5);

  vColor = vec3(0.0);
  vNorm = 0.0;
  vArcPx = 0.0;
  vREff = 0.0;
  vTotalLen = 1.0;
  vOpacity = 0.0;
  vTexHash = 0.0;
  if (vc < 2) {
    /* worker.js: fewer than two points draws nothing. */
    gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
    return;
  }

  int vid_i = int(vid + 0.5);
  int i = min(vid_i / 2, vc - 1);
  float side = (vid_i % 2 == 0) ? -1.0 : 1.0;

  vec4 v = texelFetch(uVerts, vert_texel(stroke, i), 0);
  vec2 p = v.xy;
  float arc = v.z;
  float radius = h1.w;
  float total_len = max(h1.z, 1e-6);

  /* Tangent: segment direction at the ends, bisector in between. */
  vec2 t_in = vec2(0.0);
  vec2 t_out = vec2(0.0);
  if (i > 0) {
    t_in = p - point_at(stroke, i - 1);
    t_in = (dot(t_in, t_in) > 1e-12) ? normalize(t_in) : vec2(0.0);
  }
  if (i + 1 < vc) {
    t_out = point_at(stroke, i + 1) - p;
    t_out = (dot(t_out, t_out) > 1e-12) ? normalize(t_out) : vec2(0.0);
  }
  vec2 tang = (i == 0) ? t_out : ((i + 1 == vc) ? t_in : t_in + t_out);
  tang = (dot(tang, tang) > 1e-8) ? normalize(tang) : vec2(1.0, 0.0);
  vec2 nrm = vec2(-tang.y, tang.x);

  float taper = (TEX_STRENGTH > 0.0) ? taper_at(arc / total_len, clamp(TEX_TAPER, 0.0, 1.0)) : 1.0;
  float r_eff = radius * taper;

  /* Miter so the ribbon edges meet at a bend; clamped against hairpins. */
  float miter = 1.0;
  if (i > 0 && i + 1 < vc) {
    vec2 n_in = vec2(-t_in.y, t_in.x);
    miter = clamp(1.0 / max(abs(dot(nrm, n_in)), 0.25), 1.0, 4.0);
  }
  /* Push the end points out by a radius so the round caps have geometry. */
  float cap = 0.0;
  if (i == 0) {
    cap = -r_eff;
  }
  else if (i + 1 == vc) {
    cap = r_eff;
  }
  vec2 pos = p + nrm * (r_eff * miter * side) + tang * cap;
  gl_Position = vec4(pos / IMG_SIZE * 2.0 - 1.0, 0.0, 1.0);

  vColor = h0.rgb;
  vOpacity = h0.a;
  vNorm = side;
  vArcPx = arc + cap;
  vREff = r_eff;
  vTotalLen = total_len;
  vTexHash = h1.y;
}
