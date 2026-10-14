/* Kang 2007 tangent filter, with a texture reduction instead of an SSBO maximum. */
void main() {
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  ivec2 size = ivec2(IMG_SIZE);
  if (any(greaterThanEqual(px, size))) return;
  vec4 c = texelFetch(uField, px, 0);
  float len = length(c.xy);
  int r = int(ETF_RADIUS);
  if (len < 1e-8 || r < 1) { imageStore(uOut, px, c); return; }
  vec2 tc = vec2(-c.y, c.x) / len;
  float gmax = max(texelFetch(uMax, ivec2(0), 0).r, 1e-6);
  vec2 sum = vec2(0.0);
  for (int dy=-r; dy<=r; ++dy) for (int dx=-r; dx<=r; ++dx) {
    if (dx*dx+dy*dy > r*r) continue;
    vec4 other = texelFetch(uField, clamp(px+ivec2(dx,dy), ivec2(0), size-1), 0);
    float ol = length(other.xy);
    if (ol < 1e-8) continue;
    vec2 to = vec2(-other.y,other.x) / ol;
    float d = dot(tc,to);
    float wm = 0.5 * (1.0 + tanh((other.z-c.z) / gmax));
    sum += (d >= 0.0 ? 1.0 : -1.0) * to * wm * abs(d);
  }
  vec2 tn = length(sum)>1e-8 ? normalize(sum) : tc;
  imageStore(uOut,px,vec4(vec2(tn.y,-tn.x)*len,c.z,0.0));
}
