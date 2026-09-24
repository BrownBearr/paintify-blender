/* Small whole-image writes: importing the source, copying a target, and the
 * flat underpaints. Mode 0 clamps and makes opaque, 1 copies exactly, 2 fills
 * with uFill, 3 fills with the mean that mean.glsl left in texel (0, 0). */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  vec4 c;
  if (uMode == 0) {
    c = vec4(clamp(texelFetch(uIn, px, 0).rgb, 0.0, 1.0), 1.0);
  }
  else if (uMode == 1) {
    c = texelFetch(uIn, px, 0);
  }
  else if (uMode == 2) {
    c = vec4(clamp(uFill.rgb, 0.0, 1.0), 1.0);
  }
  else {
    vec4 sum = texelFetch(uIn, ivec2(0, 0), 0);
    c = vec4(clamp(sum.rgb / max(sum.a, 1.0), 0.0, 1.0), 1.0);
  }
  imageStore(uOut, px, c);
}
