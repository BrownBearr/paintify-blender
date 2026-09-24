/* Per-pixel maps. Mode 0: Lab distance between the layer reference (uA) and
 * the canvas (uB), Hertzmann's placement error. Mode 1: mean absolute
 * channel difference between this frame's source (uA) and the previous one
 * (uB) on worker.js's 0..255 frameDiffThreshold scale. */
void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  vec3 a = texelFetch(uA, px, 0).rgb;
  vec3 b = texelFetch(uB, px, 0).rgb;
  float v;
  if (uMode == 0) {
    v = length(rgb_to_lab(clamp(a, 0.0, 1.0)) - rgb_to_lab(clamp(b, 0.0, 1.0)));
  }
  else {
    vec3 d = abs(a - b);
    v = (d.r + d.g + d.b) / 3.0 * 255.0;
  }
  imageStore(uOut, px, vec4(v, 0.0, 0.0, 0.0));
}
