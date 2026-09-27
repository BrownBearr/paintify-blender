/* Seed cells of one Paintify Scene layer. Only object pixels that no stroke
 * of this layer covers yet count (uCover.g below COVERED): surface the camera
 * has not seen before, or that stretched open. A cell seeds when at least a
 * quarter of it is such a hole; it writes (mean hole error, argmax x, argmax
 * y, 0), otherwise the sentinel y = -1. Covered surface never seeds again,
 * which is what keeps the stroke store bounded.
 *
 * The coarsest layer (uGrid.y set) seeds from a sixteenth: surface turning
 * into view arrives as slivers narrower than its cells, and it should get
 * the same coarse strokes as the rest rather than only fine ones.
 * uGrid is (spacing, coarsest layer, cells x, cells y). */
#define COVERED 0.5

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
  int holes = 0;
  int area = 0;
  ivec2 best_px = c0;
  for (int y = c0.y; y < c1.y; ++y) {
    for (int x = c0.x; x < c1.x; ++x) {
      area += 1;
      ivec2 p = ivec2(x, y);
      if (texelFetch(uGPos, p, 0).w < 0.5 || texelFetch(uCover, p, 0).g >= COVERED) {
        continue;
      }
      holes += 1;
      float e = texelFetch(uErr, p, 0).r;
      sum += e;
      float j = e + hash01(uint(x) * 73856093u ^ uint(y) * 19349663u) * 1e-3;
      if (j > best) {
        best = j;
        best_px = p;
      }
    }
  }
  if (holes == 0 || holes * ((uGrid.y != 0) ? 16 : 4) < area) {
    imageStore(uOut, cell, vec4(-1.0, -1.0, -1.0, 0.0));
    return;
  }
  imageStore(uOut, cell, vec4(sum / float(holes), float(best_px.x), float(best_px.y), 0.0));
}
