/* One invocation per seed-grid cell: (mean error, argmax x, argmax y, max
 * source difference). uGrid is (spacing, temporal, cells x, cells y). */
void main()
{
  ivec2 cell = ivec2(gl_GlobalInvocationID.xy);
  if (cell.x >= uGrid.z || cell.y >= uGrid.w) {
    return;
  }
  int grid = max(1, uGrid.x);
  ivec2 c0 = cell * grid;
  ivec2 c1 = min(c0 + ivec2(grid), uSize);
  float sum = 0.0;
  float best = -1.0;
  float max_diff = 0.0;
  int count = 0;
  ivec2 best_px = c0;
  for (int y = c0.y; y < c1.y; ++y) {
    for (int x = c0.x; x < c1.x; ++x) {
      float e = texelFetch(uErr, ivec2(x, y), 0).r;
      sum += e;
      count += 1;
      /* worker.js breaks ties with a tiny random nudge so flat cells do not
       * all seed at one corner; a pixel hash gives the same scatter. */
      float j = e + hash01(uint(x) * 73856093u ^ uint(y) * 19349663u) * 1e-3;
      if (j > best) {
        best = j;
        best_px = ivec2(x, y);
      }
      /* The max, not the mean: one moving edge must repaint its cell. */
      if (uGrid.y != 0) {
        max_diff = max(max_diff, texelFetch(uDiff, ivec2(x, y), 0).r);
      }
    }
  }
  float mean_err = (count > 0) ? sum / float(count) : 0.0;
  imageStore(uOut, cell, vec4(mean_err, float(best_px.x), float(best_px.y), max_diff));
}
