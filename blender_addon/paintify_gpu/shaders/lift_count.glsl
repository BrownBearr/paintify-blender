/* First half of lifting freshly traced strokes onto the surface. Walks each
 * stroke of uRange (first slot, count) through the G-buffer and keeps it up
 * to the first vertex that leaves the seed's object or jumps in depth more
 * than the surface's own slope explains (a silhouette), so a stroke never
 * spans two surfaces. A floor seen at a grazing angle changes depth quickly
 * but smoothly, and keeps its strokes. The truncated count is written back,
 * so this frame draws exactly what later frames will redraw, and uFlags gets
 * 1 for each stroke that keeps two or more vertices.
 *
 * A stroke seeded within spill reach of a nearer surface (uShadow, see
 * shadow.glsl) is drawn but not flagged: it answers the nearer object's
 * brushwork in this view only, so it is painted afresh each frame, as the
 * screen painter would, instead of staying on the surface.
 *
 * uRange: (first slot, count, draw order step, unused). Flags go in draw
 * order (instance k draws slot (k * step) % count, see stroke_vert.glsl), so
 * the store keeps the order in which this frame layers the strokes. */
#define JUMP_SLACK 0.02

ivec2 pixel_of(vec2 p)
{
  return clamp(ivec2(floor(p)), ivec2(0), ivec2(IMG_SIZE) - ivec2(1));
}

/* Depth change per pixel along one axis, from the smoother side, ignoring
 * neighbours on other surfaces. */
float axis_slope(ivec2 p, ivec2 dir, float depth, float slot)
{
  ivec2 size = ivec2(IMG_SIZE);
  float best = 1e30;
  for (int s = -1; s <= 1; s += 2) {
    ivec2 q = p + dir * s;
    if (q.x >= 0 && q.y >= 0 && q.x < size.x && q.y < size.y &&
        abs(texelFetch(uGPos, q, 0).w - slot) <= 0.5) {
      best = min(best, abs(texelFetch(uGDepth, q, 0).r - depth));
    }
  }
  return (best < 1e29) ? best : 0.0;
}

float depth_slope(ivec2 p, float depth, float slot)
{
  return axis_slope(p, ivec2(1, 0), depth, slot) + axis_slope(p, ivec2(0, 1), depth, slot);
}

void main()
{
  int k = int(gl_GlobalInvocationID.x);
  if (k >= uRange.y) {
    return;
  }
  int stroke = uRange.x + int((uint(k) * uint(uRange.z)) % uint(max(uRange.y, 1)));
  vec4 h1 = imageLoad(uHeads, head_texel(stroke, 1));
  int vc = int(h1.x + 0.5);
  int kept = 0;
  if (vc >= 2) {
    vec2 p = texelFetch(uVerts, vert_texel(stroke, 0), 0).xy;
    ivec2 ip = pixel_of(p);
    float slot = texelFetch(uGPos, ip, 0).w;
    if (slot >= 0.5) {
      kept = 1;
      float prev = texelFetch(uGDepth, ip, 0).r;
      float prev_slope = depth_slope(ip, prev, slot);
      for (int i = 1; i < vc; ++i) {
        vec2 q = texelFetch(uVerts, vert_texel(stroke, i), 0).xy;
        ip = pixel_of(q);
        if (abs(texelFetch(uGPos, ip, 0).w - slot) > 0.5) {
          break;
        }
        float depth = texelFetch(uGDepth, ip, 0).r;
        float slope = depth_slope(ip, depth, slot);
        float allowed = 2.0 * max(slope, prev_slope) * distance(p, q) +
                        JUMP_SLACK * max(depth, prev);
        if (abs(depth - prev) > allowed) {
          break;
        }
        kept += 1;
        p = q;
        prev = depth;
        prev_slope = slope;
      }
    }
  }
  if (kept < 2) {
    kept = 0;
  }
  if (kept != vc) {
    h1.x = float(kept);
    if (kept > 0) {
      h1.z = max(texelFetch(uVerts, vert_texel(stroke, kept - 1), 0).z, 1e-6);
    }
    imageStore(uHeads, head_texel(stroke, 1), h1);
  }
  bool keep = kept >= 2 &&
              texelFetch(uShadow, pixel_of(texelFetch(uVerts, vert_texel(stroke, 0), 0).xy), 0).r < 0.5;
  imageStore(uFlags, list_texel(uRange.x + k), vec4(keep ? 1.0 : 0.0, 0.0, 0.0, 0.0));
}
