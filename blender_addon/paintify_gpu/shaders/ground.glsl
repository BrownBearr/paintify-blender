void main() {
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (any(greaterThanEqual(px, ivec2(IMG_SIZE)))) return;
  vec3 source = texelFetch(uIn, px, 0).rgb;
  imageStore(uOut, px, vec4(mix(ST_GROUND, styleColor(source, 0u, false),
                              clamp(ST_UNDER_OPACITY, 0.0, 1.0)), 1.0));
}
