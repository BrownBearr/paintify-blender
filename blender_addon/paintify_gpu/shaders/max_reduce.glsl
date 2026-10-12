void main() {
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  ivec2 size = textureSize(uIn, 0);
  ivec2 output_size = (size + ivec2(15)) / 16;
  if (any(greaterThanEqual(px, output_size))) return;
  float maximum = 0.0;
  for (int y=0; y<16; ++y) for (int x=0; x<16; ++x) {
    ivec2 q = px*16 + ivec2(x,y);
    if (all(lessThan(q, size))) {
      vec4 value = texelFetch(uIn, q, 0);
      maximum = max(maximum, uMode == 0 ? value.z : value.x);
    }
  }
  imageStore(uOut, px, vec4(maximum));
}
