/* Separable max filter over the source-difference map, one axis per pass.
 * Strokes reach past the cell they were seeded in, so a change must repaint
 * a neighbourhood, not just the pixels that changed. uDir.xy is the step,
 * uDir.zw the image size. */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  ivec2 size = uDir.zw;
  if (px.x >= size.x || px.y >= size.y) {
    return;
  }
  float m = 0.0;
  for (int d = -uRadius; d <= uRadius; ++d) {
    ivec2 q = clamp(px + uDir.xy * d, ivec2(0), size - ivec2(1));
    m = max(m, texelFetch(uIn, q, 0).r);
  }
  imageStore(uOut, px, vec4(m, 0.0, 0.0, 0.0));
}
