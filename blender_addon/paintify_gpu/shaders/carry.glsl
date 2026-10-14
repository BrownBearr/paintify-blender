/* Temporal underpaint. Where the (dilated) source difference passes the
 * stability threshold, start from the fresh Gaussian ground, so strokes of
 * whatever used to be there cannot survive as a trail. Elsewhere keep last
 * frame's paint. */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  vec4 c;
  if (texelFetch(uMask, px, 0).r >= uThreshold) {
    c = vec4(clamp(texelFetch(uFresh, px, 0).rgb, 0.0, 1.0), 1.0);
  }
  else {
    c = texelFetch(uPrev, px, 0);
  }
  imageStore(uOut, px, c);
}
