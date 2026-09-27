/* Per-frame object table of Paintify Scene, one row of TABLE_TEXELS texels
 * per slot: the rows of the model-view-projection matrix (0-3), the z row of
 * the model-view matrix (4) and the first three rows of the model matrix
 * (5-7). Slot 0 is the world; a slot whose object is gone this frame is all
 * zeros, so its strokes project to w = 0 and are dropped.
 *
 * uView: (pixels per world unit at view depth 1 for a perspective camera, or
 * everywhere for an orthographic one; 1 if perspective; unused; unused). */
vec4 table_row(int slot, int r)
{
  return texelFetch(uTable, ivec2(r, slot), 0);
}

/* Clip position of anchor `a` stored in `slot`'s space; its view depth goes
 * to `depth`. */
vec4 anchor_clip(int slot, vec3 a, out float depth)
{
  vec4 p = vec4(a, 1.0);
  depth = -dot(table_row(slot, 4), p);
  return vec4(dot(table_row(slot, 0), p), dot(table_row(slot, 1), p),
              dot(table_row(slot, 2), p), dot(table_row(slot, 3), p));
}

vec3 anchor_to_world(int slot, vec3 a)
{
  vec4 p = vec4(a, 1.0);
  return vec3(dot(table_row(slot, 5), p), dot(table_row(slot, 6), p), dot(table_row(slot, 7), p));
}

float px_per_unit(float depth)
{
  return (uView.y > 0.5) ? uView.x / max(depth, 1e-6) : uView.x;
}

vec2 clip_to_px(vec4 clip)
{
  return (clip.xy / clip.w * 0.5 + 0.5) * IMG_SIZE;
}
