/* Paintify Scene: redraws stored strokes where their surface is now. Each
 * vertex is an anchor in object (or world) space; it goes through its slot's
 * current matrices to the screen, and its width follows the distance, so the
 * stroke stays painted on the surface as the object or camera moves. Every
 * length handed to the fragment stage stays in the pixels of the frame the
 * stroke was painted in, which keeps coverage and brush texture fixed on it.
 *
 * uDraw: (first stroke, count, recolour, retire). With recolour, a stroke
 * takes its colour offset from the current reference at its seed, so shading
 * follows the light while each stroke keeps its own jitter.
 *
 * With retire (every layer but the coarsest), a stroke fades out where the
 * coarser paint beneath it (uErr, before this layer draws) already matches
 * the reference: detail painted for one view, such as the edge of an object
 * that has since moved on, does not stay behind as clutter. Seeding needs the
 * full threshold, so a stroke between the two neither comes nor goes. Pixels
 * in reach of a nearer surface's spill (uShadow) are no evidence either way. */
#define MIN_RADIUS_PX 0.75
#define SQUASH_GONE 0.2
#define SQUASH_FULL 0.45
#define STRETCH_FULL 1.8
#define STRETCH_GONE 3.0
#define RETIRE_GONE 0.25
#define RETIRE_FULL 0.5

/* Screen position of vertex i; its painted arc length goes to `arc`. */
vec2 project_vertex(int stroke, int slot, int i, out float depth, out float arc, out bool ok)
{
  vec4 a = texelFetch(uAnchors, vert_texel(stroke, i), 0);
  vec4 clip = anchor_clip(slot, a.xyz, depth);
  arc = a.w;
  ok = clip.w > 1e-6;
  return ok ? clip_to_px(clip) : vec2(0.0);
}

void main()
{
  int stroke = uDraw.x + gl_InstanceID;
  vec4 h0 = texelFetch(uSHeads, shead_texel(stroke, 0), 0);
  vec4 h1 = texelFetch(uSHeads, shead_texel(stroke, 1), 0);
  vec4 h2 = texelFetch(uSHeads, shead_texel(stroke, 2), 0);
  vec4 h3 = texelFetch(uSHeads, shead_texel(stroke, 3), 0);
  int vc = int(h1.x + 0.5);
  int slot = int(h3.y + 0.5);

  vColor = vec3(0.0);
  vNorm = 0.0;
  vArcPx = 0.0;
  vREff = 0.0;
  vTotalLen = 1.0;
  vOpacity = 0.0;
  vTexHash = 0.0;
  vVis = 0.0;
  vDepth = 0.0;
  vDepthTol = 0.0;
  gl_Position = vec4(0.0, 0.0, 2.0, 1.0);

  int vid_i = int(vid + 0.5);
  int i = min(vid_i / 2, max(vc - 1, 0));
  float side = (vid_i % 2 == 0) ? -1.0 : 1.0;
  float depth;
  float arc;
  bool ok;
  vec2 p = project_vertex(stroke, slot, i, depth, arc, ok);
  if (vc < 2 || !ok) {
    return;
  }

  /* Tangent from the neighbours, and how much of their painted distance
   * survives on screen now. */
  vec2 t_in = vec2(0.0);
  vec2 t_out = vec2(0.0);
  float seg_now = 0.0;
  float seg_painted = 0.0;
  float nd;
  float narc;
  bool nok;
  if (i > 0) {
    vec2 q = project_vertex(stroke, slot, i - 1, nd, narc, nok);
    t_in = p - q;
    if (nok) {
      seg_now += length(t_in);
      seg_painted += arc - narc;
    }
    t_in = (nok && dot(t_in, t_in) > 1e-12) ? normalize(t_in) : vec2(0.0);
  }
  if (i + 1 < vc) {
    vec2 q = project_vertex(stroke, slot, i + 1, nd, narc, nok);
    t_out = q - p;
    if (nok) {
      seg_now += length(t_out);
      seg_painted += narc - arc;
    }
    t_out = (nok && dot(t_out, t_out) > 1e-12) ? normalize(t_out) : vec2(0.0);
  }
  vec2 tang = (i == 0) ? t_out : ((i + 1 == vc) ? t_in : t_in + t_out);
  tang = (dot(tang, tang) > 1e-8) ? normalize(tang) : vec2(1.0, 0.0);
  vec2 nrm = vec2(-tang.y, tang.x);

  float radius = h1.w;
  float total_len = max(h1.z, 1e-6);
  float taper = (TEX_STRENGTH > 0.0) ? taper_at(arc / total_len, clamp(TEX_TAPER, 0.0, 1.0)) : 1.0;
  float r_eff = radius * taper;
  /* Painted-frame pixels to current pixels, from the world-space radius. */
  float scale = h3.x * px_per_unit(depth) / max(radius, 1e-6);
  float r_now = max(r_eff * scale, MIN_RADIUS_PX);

  float miter = 1.0;
  if (i > 0 && i + 1 < vc) {
    vec2 n_in = vec2(-t_in.y, t_in.x);
    /* Tighter than the screen strokes: a foreshortened polyline zigzags. */
    miter = clamp(1.0 / max(abs(dot(nrm, n_in)), 0.5), 1.0, 2.0);
  }
  float cap = 0.0;
  if (i == 0) {
    cap = -1.0;
  }
  else if (i + 1 == vc) {
    cap = 1.0;
  }
  vec2 pos = p + nrm * (r_now * miter * side) + tang * (cap * r_now);
  gl_Position = vec4(pos / IMG_SIZE * 2.0 - 1.0, 0.0, 1.0);

  float vis = 1.0;
  /* A stroke seen edge-on collapses into a twisted sliver, and one painted
   * edge-on smears once it turns to face the camera: fade either out and let
   * the hole be repainted from this view. */
  if (seg_painted > 1e-3) {
    float stretch = seg_now / (seg_painted * scale);
    vis = smoothstep(SQUASH_GONE, SQUASH_FULL, stretch) *
          (1.0 - smoothstep(STRETCH_FULL, STRETCH_GONE, stretch));
  }

  /* Occlusion is tested per fragment against the G-buffer (stroke_frag.glsl),
   * so a stroke stops exactly at the edge of whatever passes in front. The
   * tolerance covers the surface's depth slope across the ribbon's width. */
  ivec2 size = ivec2(IMG_SIZE);
  ivec2 ip = clamp(ivec2(floor(p)), ivec2(0), size - ivec2(1));
  float g = texelFetch(uGDepth, ip, 0).r;
  float gx = texelFetch(uGDepth, min(ip + ivec2(1, 0), size - ivec2(1)), 0).r;
  float gy = texelFetch(uGDepth, min(ip + ivec2(0, 1), size - ivec2(1)), 0).r;
  float slope = 0.0;
  if (g < 1e29 && gx < 1e29) {
    slope += abs(gx - g);
  }
  if (g < 1e29 && gy < 1e29) {
    slope += abs(gy - g);
  }
  vDepth = depth;
  vDepthTol = 0.005 * depth + 2.0 / px_per_unit(depth) + (2.0 + r_now * miter) * slope;

  if (uDraw.w != 0) {
    float err = 0.0;
    float samples = 0.0;
    for (int j = 0; j < 3; ++j) {
      int vj = (j == 0) ? 0 : ((j == 1) ? (vc - 1) / 2 : vc - 1);
      float dj;
      float aj;
      bool okj;
      ivec2 qj = ivec2(floor(project_vertex(stroke, slot, vj, dj, aj, okj)));
      /* Near a nearer surface the error is its spill, not this surface. */
      if (okj && qj.x >= 0 && qj.y >= 0 && qj.x < size.x && qj.y < size.y &&
          texelFetch(uShadow, qj, 0).r < 0.5) {
        err += texelFetch(uErr, qj, 0).r;
        samples += 1.0;
      }
    }
    if (samples > 0.0) {
      vis *= smoothstep(RETIRE_GONE * THRESHOLD, RETIRE_FULL * THRESHOLD, err / samples);
    }
  }

  /* Recolour from the seed, or the middle or end if something now hides the
   * seed: never from whatever passes in front. Fully hidden keeps its paint. */
  vec3 col = h0.rgb;
  if (uDraw.z != 0) {
    for (int j = 0; j < 3; ++j) {
      int vj = (j == 0) ? 0 : ((j == 1) ? (vc - 1) / 2 : vc - 1);
      float dj;
      float aj;
      bool okj;
      ivec2 qj = ivec2(floor(project_vertex(stroke, slot, vj, dj, aj, okj)));
      if (okj && qj.x >= 0 && qj.y >= 0 && qj.x < size.x && qj.y < size.y &&
          dj <= texelFetch(uGDepth, qj, 0).r + 0.01 * dj + 2.0 / px_per_unit(dj)) {
        col = clamp(h0.rgb + texelFetch(uRef, qj, 0).rgb - h2.rgb, 0.0, 1.0);
        break;
      }
    }
  }

  vColor = col;
  vOpacity = h0.a;
  vNorm = side;
  vArcPx = arc + cap * r_eff;
  vREff = r_eff;
  vTotalLen = total_len;
  vTexHash = h1.y;
  vVis = vis;
}
