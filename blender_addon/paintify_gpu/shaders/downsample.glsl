/* Explicit luma pyramid; Blender's Python GPU API does not expose mip building. */
void main() {
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (any(greaterThanEqual(px, uSize))) return;
  ivec2 input_size = textureSize(uIn, 0);
  vec2 center = (vec2(px) + 0.5) * vec2(input_size) / vec2(uSize);
  vec3 rgb = vec3(0.0);
  for (int y=0; y<2; ++y) for (int x=0; x<2; ++x) {
    ivec2 q = clamp(ivec2(floor(center + vec2(x,y) - 0.5)), ivec2(0), input_size-1);
    rgb += texelFetch(uIn, q, 0).rgb * 0.25;
  }
  if (uLuma != 0) rgb = vec3(dot(rgb, vec3(0.299, 0.587, 0.114)));
  imageStore(uOut, px, vec4(rgb, 1.0));
}
