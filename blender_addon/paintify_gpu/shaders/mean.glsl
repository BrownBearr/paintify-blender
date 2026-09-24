/* Image mean for the pointillist 'average' underpaint, in two passes: mode 0
 * sums 16x16 tiles, mode 1 sums the tiles into texel (0, 0). The result holds
 * the colour sum in rgb and the pixel count in a. */
void main()
{
  ivec2 tile_id = ivec2(gl_GlobalInvocationID.xy);
  if (uMode == 0) {
    ivec2 c0 = tile_id * 16;
    if (c0.x >= uSize.x || c0.y >= uSize.y) {
      return;
    }
    ivec2 c1 = min(c0 + ivec2(16), uSize);
    vec3 sum = vec3(0.0);
    for (int y = c0.y; y < c1.y; ++y) {
      for (int x = c0.x; x < c1.x; ++x) {
        sum += texelFetch(uIn, ivec2(x, y), 0).rgb;
      }
    }
    imageStore(uOut, tile_id, vec4(sum, float((c1.x - c0.x) * (c1.y - c0.y))));
    return;
  }
  if (tile_id.x != 0 || tile_id.y != 0) {
    return;
  }
  vec4 sum = vec4(0.0);
  for (int y = 0; y < uSize.y; ++y) {
    for (int x = 0; x < uSize.x; ++x) {
      sum += texelFetch(uIn, ivec2(x, y), 0);
    }
  }
  imageStore(uOut, ivec2(0, 0), sum);
}
