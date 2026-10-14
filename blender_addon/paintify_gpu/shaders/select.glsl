/* Paintify Scene's underpaint: the screen painting (uA) over the background,
 * the style's underpaint (uB: the coarsest Gaussian, the image mean or white)
 * wherever an attachable object covers the pixel,
 * so screen strokes never show through gaps between object strokes. */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  vec4 c = texelFetch(uA, px, 0);
  if (texelFetch(uGPos, px, 0).w >= 0.5) {
    c = vec4(clamp(texelFetch(uB, px, 0).rgb, 0.0, 1.0), 1.0);
  }
  imageStore(uOut, px, c);
}
