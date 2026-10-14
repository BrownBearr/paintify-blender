/* Stream compaction without atomics, which Blender's Python GPU API lacks.
 * uScan: (mode, flags, layer, store capacity).
 *
 * Mode 0: one invocation per block of SCAN_BLOCK flags writes the block's sum.
 * Mode 1: one invocation turns the sums into exclusive prefixes (y) and
 * advances the layer's counter texel: (stored strokes, first slot of this
 * frame's strokes, strokes requested, unused). A few thousand blocks at most,
 * so a serial loop is cheaper than more dispatches. */
void main()
{
  int n = uScan.y;
  int blocks = (n + SCAN_BLOCK - 1) / SCAN_BLOCK;
  int b = int(gl_GlobalInvocationID.x);
  if (uScan.x == 0) {
    if (b >= blocks) {
      return;
    }
    float sum = 0.0;
    int end = min(n, (b + 1) * SCAN_BLOCK);
    for (int k = b * SCAN_BLOCK; k < end; ++k) {
      sum += texelFetch(uFlags, list_texel(k), 0).r;
    }
    imageStore(uBlocks, list_texel(b), vec4(sum, 0.0, 0.0, 0.0));
    return;
  }
  if (b != 0) {
    return;
  }
  ivec2 at = ivec2(uScan.z, 0);
  float base = imageLoad(uCounter, at).x;
  float run = 0.0;
  for (int k = 0; k < blocks; ++k) {
    vec4 v = imageLoad(uBlocks, list_texel(k));
    imageStore(uBlocks, list_texel(k), vec4(v.x, run, 0.0, 0.0));
    run += v.x;
  }
  imageStore(uCounter, at, vec4(min(float(uScan.w), base + run), base, base + run, 0.0));
}
