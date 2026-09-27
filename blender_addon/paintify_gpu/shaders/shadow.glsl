/* Paintify Scene: which pixels lie within reach of a nearer surface's
 * strokes. Brushwork spills over its object's silhouette onto whatever is
 * behind; that surface must not read the spill as error and anchor strokes
 * to correct it, or they stay behind as clutter once the object moves on.
 *
 * Separable: mode 0 writes the nearest depth over a row of 2 * radius + 1
 * pixels, mode 1 the nearest over a column of those, compared with the
 * pixel's own depth: 1 where something within the window is nearer by more
 * than the surface's own slope explains, else 0.
 * uShadow: (mode, radius, unused, unused). */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  ivec2 size = ivec2(IMG_SIZE);
  if (px.x >= size.x || px.y >= size.y) {
    return;
  }
  int radius = max(uShadow.y, 1);
  float near = 1e30;
  if (uShadow.x == 0) {
    for (int d = -radius; d <= radius; ++d) {
      ivec2 q = clamp(px + ivec2(d, 0), ivec2(0), size - ivec2(1));
      near = min(near, texelFetch(uGDepth, q, 0).r);
    }
    imageStore(uOut, px, vec4(near, 0.0, 0.0, 0.0));
    return;
  }
  for (int d = -radius; d <= radius; ++d) {
    ivec2 q = clamp(px + ivec2(0, d), ivec2(0), size - ivec2(1));
    near = min(near, texelFetch(uIn, q, 0).r);
  }
  float depth = texelFetch(uGDepth, px, 0).r;
  float shadow = 0.0;
  if (depth < 1e29) {
    float sx = abs(texelFetch(uGDepth, min(px + ivec2(1, 0), size - ivec2(1)), 0).r - depth);
    float sy = abs(texelFetch(uGDepth, min(px + ivec2(0, 1), size - ivec2(1)), 0).r - depth);
    float slope = min(sx, 1e3) + min(sy, 1e3);
    /* A one-pixel step onto another surface is no slope. */
    slope = min(slope, 0.05 * depth);
    shadow = (near < depth - (0.02 * depth + 1.5 * slope * float(radius))) ? 1.0 : 0.0;
  }
  imageStore(uOut, px, vec4(shadow, 0.0, 0.0, 0.0));
}
