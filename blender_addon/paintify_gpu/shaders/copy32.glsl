/* Exact texel copy into an RGBA32F target, used to grow a scene stroke store
 * without losing its strokes. uSize is the region to copy. */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  imageStore(uOut, px, texelFetch(uIn, px, 0));
}
