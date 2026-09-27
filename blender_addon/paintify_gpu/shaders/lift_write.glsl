/* Second half of lifting: appends every flagged stroke to the layer's scene
 * store at (stored count + prefix of flags before it). Each vertex becomes
 * the surface point under it, in the object's own space (or the world's when
 * uRange.w is set), read bilinearly from the G-buffer so the stroke lands
 * where it was drawn to a fraction of a pixel. Strokes past the store's
 * capacity are dropped; they were still drawn this frame.
 * uRange: (strokes, layer, capacity, world anchors); uOrder: (slots per pass,
 * draw order step, unused, unused). Invocation k is the k-th stroke in draw
 * order, as lift_count.glsl flagged them. */
ivec2 pixel_of(vec2 p)
{
  return clamp(ivec2(floor(p)), ivec2(0), ivec2(IMG_SIZE) - ivec2(1));
}

vec3 surface_at(vec2 p, float slot, float depth)
{
  vec3 nearest = texelFetch(uGPos, pixel_of(p), 0).xyz;
  vec2 q = p - 0.5;
  ivec2 i0 = ivec2(floor(q));
  ivec2 size = ivec2(IMG_SIZE);
  if (i0.x < 0 || i0.y < 0 || i0.x + 1 >= size.x || i0.y + 1 >= size.y) {
    return nearest;
  }
  vec2 f = q - vec2(i0);
  vec4 a = texelFetch(uGPos, i0, 0);
  vec4 b = texelFetch(uGPos, i0 + ivec2(1, 0), 0);
  vec4 c = texelFetch(uGPos, i0 + ivec2(0, 1), 0);
  vec4 d = texelFetch(uGPos, i0 + ivec2(1, 1), 0);
  float da = texelFetch(uGDepth, i0, 0).r;
  float db = texelFetch(uGDepth, i0 + ivec2(1, 0), 0).r;
  float dc = texelFetch(uGDepth, i0 + ivec2(0, 1), 0).r;
  float dd = texelFetch(uGDepth, i0 + ivec2(1, 1), 0).r;
  float tol = 0.05 * depth;
  /* Interpolate only within one continuous surface. */
  if (abs(a.w - slot) > 0.5 || abs(b.w - slot) > 0.5 || abs(c.w - slot) > 0.5 ||
      abs(d.w - slot) > 0.5 || abs(da - depth) > tol || abs(db - depth) > tol ||
      abs(dc - depth) > tol || abs(dd - depth) > tol) {
    return nearest;
  }
  return mix(mix(a.xyz, b.xyz, f.x), mix(c.xyz, d.xyz, f.x), f.y);
}

void main()
{
  int k = int(gl_GlobalInvocationID.x);
  if (k >= uRange.x || texelFetch(uFlags, list_texel(k), 0).r < 0.5) {
    return;
  }
  int block = k / SCAN_BLOCK;
  float local = 0.0;
  for (int j = block * SCAN_BLOCK; j < k; ++j) {
    local += texelFetch(uFlags, list_texel(j), 0).r;
  }
  float base = texelFetch(uCounter, ivec2(uRange.y, 0), 0).y;
  int dst = int(base + texelFetch(uBlocks, list_texel(block), 0).y + local + 0.5);
  if (dst >= uRange.z) {
    return;
  }

  int slots = max(uOrder.x, 1);
  int stroke = (k / slots) * slots + int((uint(k % slots) * uint(uOrder.y)) % uint(slots));
  vec4 h0 = texelFetch(uHeads, head_texel(stroke, 0), 0);
  vec4 h1 = texelFetch(uHeads, head_texel(stroke, 1), 0);
  int count = int(h1.x + 0.5);
  ivec2 ip0 = pixel_of(texelFetch(uVerts, vert_texel(stroke, 0), 0).xy);
  float slot = floor(texelFetch(uGPos, ip0, 0).w + 0.5);
  bool world = uRange.w != 0;
  for (int i = 0; i < count; ++i) {
    vec4 v = texelFetch(uVerts, vert_texel(stroke, i), 0);
    float depth = texelFetch(uGDepth, pixel_of(v.xy), 0).r;
    vec3 a = surface_at(v.xy, slot, depth);
    if (world) {
      a = anchor_to_world(int(slot), a);
    }
    imageStore(uAnchors, vert_texel(dst, i), vec4(a, v.z));
  }
  float depth0 = texelFetch(uGDepth, ip0, 0).r;
  imageStore(uSHeads, shead_texel(dst, 0), h0);
  imageStore(uSHeads, shead_texel(dst, 1), h1);
  imageStore(uSHeads, shead_texel(dst, 2), vec4(texelFetch(uRef, ip0, 0).rgb, 0.0));
  imageStore(uSHeads, shead_texel(dst, 3),
             vec4(h1.w / px_per_unit(depth0), world ? 0.0 : slot, 0.0, 0.0));
}
