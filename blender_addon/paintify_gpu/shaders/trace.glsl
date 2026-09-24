/* Seeds and traces one stroke per slot: worker.js's cell test followed by a
 * line-for-line port of `makeCurvedStroke`.
 *
 * The standalone renderer compacted seeds with atomics. Blender's Python GPU
 * API has no storage buffers, so each pass instead owns exactly one cell of
 * every block of `chunks` consecutive cells, picked by a hashed permutation.
 * That keeps a pass scattered over the whole image, as worker.js's shuffled
 * cell list is, and makes the result independent of thread scheduling.
 *
 * uLayer: (layer index, radius, first layer, unused)
 * uSlots: (pass, passes, slots in this pass, first slot in the stroke store)
 * uGrid:  (cells x, cells y, temporal, unused) */

int pass_member(int block, int pass_index, int passes, int layer)
{
  uint salt = uint(layer + 1) * 0x9e3779b9u;
  uint keys[32];
  for (int j = 0; j < passes; ++j) {
    keys[j] = hash_u(uint(block * passes + j) * 2654435761u ^ salt);
  }
  for (int j = 0; j < passes; ++j) {
    int rank = 0;
    for (int k = 0; k < passes; ++k) {
      if (keys[k] < keys[j] || (keys[k] == keys[j] && k < j)) {
        rank += 1;
      }
    }
    if (rank == pass_index) {
      return j;
    }
  }
  return 0;
}

void write_empty(int dst)
{
  imageStore(uHeads, head_texel(dst, 0), vec4(0.0));
  imageStore(uHeads, head_texel(dst, 1), vec4(0.0, 0.0, 1.0, 0.0));
}

void main()
{
  int slot = int(gl_GlobalInvocationID.x);
  if (slot >= uSlots.z) {
    return;
  }
  int dst = uSlots.w + slot;
  int passes = max(uSlots.y, 1);
  int layer = int(uLayer.x + 0.5);
  int cell_index = slot * passes + pass_member(slot, uSlots.x, passes, layer);
  int grid_w = uGrid.x;
  if (cell_index >= grid_w * uGrid.y) {
    write_empty(dst);
    return;
  }
  vec4 cell = texelFetch(uCells, ivec2(cell_index % grid_w, cell_index / grid_w), 0);

  /* worker.js: the coarsest layer always paints so the canvas is covered;
   * finer layers paint only where the error exceeds the threshold. */
  if (cell.x <= THRESHOLD && uLayer.z < 0.5) {
    write_empty(dst);
    return;
  }
  /* Temporal coherence: a cell whose source barely changed keeps last
   * frame's paint (frameDiffThreshold). */
  if (uGrid.z != 0 && cell.w < FRAME_DIFF) {
    write_empty(dst);
    return;
  }

  ivec2 size = ivec2(IMG_SIZE);
  ivec2 sp = clamp(ivec2(int(cell.y), int(cell.z)), ivec2(0), size - ivec2(1));
  uint salt = frame_salt();
  uint seed_hash = hash_u(uint(cell_index) ^ uint(layer + 1) * 83492791u ^ salt * 374761393u);

  float radius = max(1.0, uLayer.y * (1.0 + (hash01(seed_hash ^ 0x11u) * 2.0 - 1.0) * SIZE_JITTER));
  float opacity = clamp(OPACITY * (1.0 + (hash01(seed_hash ^ 0x22u) * 2.0 - 1.0) * OPACITY_JITTER),
                        0.0, 1.0);

  /* Colour is a point sample of the Gaussian reference, then HSV jitter. */
  vec3 stroke_ref = texelFetch(uRef, sp, 0).rgb;
  vec3 col = clamp(stroke_ref, 0.0, 1.0);
  if (JITTER_HUE > 0.0 || JITTER_SAT > 0.0 || JITTER_VAL > 0.0) {
    vec3 hsv = rgb_to_hsv(col);
    hsv.x = fract(hsv.x + (hash01(seed_hash ^ 0xa1u) * 2.0 - 1.0) * JITTER_HUE);
    hsv.y = clamp(hsv.y + (hash01(seed_hash ^ 0xb2u) * 2.0 - 1.0) * JITTER_SAT, 0.0, 1.0);
    hsv.z = clamp(hsv.z + (hash01(seed_hash ^ 0xc3u) * 2.0 - 1.0) * JITTER_VAL, 0.0, 1.0);
    col = hsv_to_rgb(hsv);
  }
  uint variant = brush_hash(sp, layer) & 0x7fffu;

  int max_len = clamp(int(MAX_STROKE_LEN), 1, MAX_VERTS - 1);
  int min_len = max(int(MIN_STROKE_LEN), 1);
  float curv = clamp(CURVATURE, 0.0, 1.0);
  /* worker.js: `step = Math.max(1, Math.round(radius))`. */
  float step_len = max(1.0, floor(radius + 0.5));

  vec2 p = vec2(sp) + 0.5;
  vec2 last = vec2(0.0);
  float arc = 0.0;
  imageStore(uVerts, vert_texel(dst, 0), vec4(p, arc, 0.0));
  int count = 1;

  uint jitter_seed = hash_u(uint(sp.x) * 73856093u ^ uint(sp.y) * 19349663u ^ salt * 9781u);
  float angle_jitter = ANGLE_JITTER * DEG_TO_RAD;

  for (int iter = 1; iter <= max_len; ++iter) {
    ivec2 ip = ivec2(floor(p));
    if (ip.x < 0 || ip.y < 0 || ip.x >= size.x || ip.y >= size.y) {
      break;
    }
    /* Stop once the canvas already matches the reference here better than
     * this stroke's colour would. */
    if (iter >= min_len) {
      vec3 r = texelFetch(uRef, ip, 0).rgb;
      vec3 c = texelFetch(uCanvas, ip, 0).rgb;
      vec3 d_canvas = abs(r - c);
      vec3 d_stroke = abs(r - stroke_ref);
      if (d_canvas.r + d_canvas.g + d_canvas.b <= d_stroke.r + d_stroke.g + d_stroke.b) {
        break;
      }
    }
    vec3 grad = texelFetch(uGrad, ip, 0).rgb;
    if (grad.z * step_len < 1e-3) {
      break;
    }
    /* Tangent = gradient rotated 90 degrees, kept on the side of travel. */
    vec2 nd = vec2(-grad.y, grad.x);
    if (dot(last, nd) < 0.0) {
      nd = -nd;
    }
    /* No previous direction on the first step: seed it from the gradient so
     * curvature 0 draws straight strokes instead of aborting. */
    if (dot(last, last) < 1e-12) {
      last = normalize(nd);
    }
    /* Hertzmann's fc filter; `nd` keeps the raw gradient magnitude. */
    nd = curv * nd + (1.0 - curv) * last;
    float nm = length(nd);
    if (nm < 1e-6) {
      break;
    }
    nd /= nm;
    if (angle_jitter > 0.0) {
      float th = (hash01(jitter_seed ^ uint(iter) * 2654435761u) * 2.0 - 1.0) * angle_jitter;
      float cs = cos(th);
      float sn = sin(th);
      nd = vec2(nd.x * cs - nd.y * sn, nd.x * sn + nd.y * cs);
    }
    vec2 next_p = p + step_len * nd;
    last = nd;
    if (next_p.x < 0.0 || next_p.y < 0.0 || next_p.x >= IMG_SIZE.x || next_p.y >= IMG_SIZE.y) {
      break;
    }
    arc += distance(next_p, p);
    p = next_p;
    imageStore(uVerts, vert_texel(dst, count), vec4(p, arc, 0.0));
    count += 1;
    if (count >= MAX_VERTS) {
      break;
    }
  }

  imageStore(uHeads, head_texel(dst, 0), vec4(col, opacity));
  imageStore(uHeads, head_texel(dst, 1), vec4(float(count), float(variant), max(arc, 1e-6), radius));
}
