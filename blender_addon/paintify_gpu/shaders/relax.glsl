/* Hertzmann 2001, "Paint By Relaxation", over the frame's stroke pool. Each
 * stroke tries a few perturbations (move a point, translate, shorten, change
 * width, rotate, recolour) and keeps the one with the lowest local energy
 *
 *   score = A * (Em + w_area - Eg)
 *
 * where A is the stroke's area, Em its mean Lab fit error and Eg the error of
 * the ground (underpaint) beneath it. See shaders/relax.comp in
 * paintify-GPU for the derivation. uRelax.x is the iteration and
 * uPool.x the number of pooled slots. */
#define SAMPLE_ROWS 8
#define SAMPLE_COLS 3

struct Stroke {
  vec2 p[MAX_VERTS];
  float radius;
  int count;
};

struct Probe {
  float em;
  float eg;
  float area;
  vec3 mean;
};

Probe probe(Stroke s, vec3 col)
{
  vec2 size = IMG_SIZE;
  float e = 0.0;
  float eg = 0.0;
  float wsum = 0.0;
  vec3 acc = vec3(0.0);
  vec3 lab_col = rgb_to_lab(col);
  int segs = max(s.count - 1, 1);
  for (int r = 0; r < SAMPLE_ROWS; ++r) {
    float t = (float(r) + 0.5) / float(SAMPLE_ROWS) * float(segs);
    int i = min(int(t), segs - 1);
    vec2 a = s.p[i];
    vec2 b = s.p[min(i + 1, s.count - 1)];
    vec2 c = mix(a, b, t - float(i));
    vec2 tang = b - a;
    float tl = length(tang);
    vec2 nrm = (tl > 1e-5) ? vec2(-tang.y, tang.x) / tl : vec2(0.0, 1.0);
    for (int q = 0; q < SAMPLE_COLS; ++q) {
      float u = (float(q) + 0.5) / float(SAMPLE_COLS) * 2.0 - 1.0;
      vec2 sp = c + nrm * (u * s.radius);
      if (sp.x < 0.0 || sp.y < 0.0 || sp.x >= size.x || sp.y >= size.y) {
        continue;
      }
      /* A stroke's coverage falls off at its edges, so they weigh less. */
      float cov = 1.0 - 0.5 * abs(u);
      ivec2 ip = ivec2(sp);
      vec3 src = texelFetch(uSrc, ip, 0).rgb;
      vec3 lab_src = rgb_to_lab(src);
      e += cov * distance(lab_col, lab_src);
      eg += cov * distance(rgb_to_lab(texelFetch(uGround, ip, 0).rgb), lab_src);
      acc += cov * src;
      wsum += cov;
    }
  }
  Probe pr;
  pr.mean = (wsum > 1e-6) ? acc / wsum : col;
  pr.em = (wsum > 1e-6) ? e / wsum : 0.0;
  pr.eg = (wsum > 1e-6) ? eg / wsum : 0.0;
  float len = 0.0;
  for (int k = 1; k < s.count; ++k) {
    len += distance(s.p[k], s.p[k - 1]);
  }
  pr.area = 2.0 * s.radius * len + 3.14159265 * s.radius * s.radius;
  return pr;
}

float score(float em, float area, float eg)
{
  return area * (em + RELAX_AREA_W - eg);
}

/* One perturbation picked by hash; `amp` shrinks over the iterations. */
Stroke perturb(Stroke s, uint h, float amp)
{
  uint kind = hash_u(h) % 5u;
  float r = max(s.radius, 0.5);
  if (kind == 0u) {
    int i = (s.count > 2) ? 1 + int(hash_u(h ^ 0x51u) % uint(s.count - 1)) : s.count - 1;
    i = min(i, s.count - 1);
    s.p[i] += (hash2(h ^ 0x62u) * 2.0 - 1.0) * r * amp;
  }
  else if (kind == 1u) {
    vec2 d = (hash2(h ^ 0x73u) * 2.0 - 1.0) * r * amp;
    for (int k = 0; k < s.count; ++k) {
      s.p[k] += d;
    }
  }
  else if (kind == 2u) {
    /* Shorten only; extrapolating walks a stroke off its feature. */
    if (s.count > 2) {
      s.count -= 1;
    }
  }
  else if (kind == 3u) {
    s.radius = clamp(s.radius * (1.0 + (hash01(h ^ 0x84u) * 2.0 - 1.0) * 0.35 * amp), 0.6, 64.0);
  }
  else {
    vec2 mid = vec2(0.0);
    for (int k = 0; k < s.count; ++k) {
      mid += s.p[k];
    }
    mid /= float(s.count);
    float th = (hash01(h ^ 0x95u) * 2.0 - 1.0) * 0.5 * amp;
    float cs = cos(th);
    float sn = sin(th);
    for (int k = 0; k < s.count; ++k) {
      vec2 d = s.p[k] - mid;
      s.p[k] = mid + vec2(d.x * cs - d.y * sn, d.x * sn + d.y * cs);
    }
  }
  return s;
}

void main()
{
  int idx = int(gl_GlobalInvocationID.x);
  if (idx >= uPool.x) {
    return;
  }
  vec4 h0 = imageLoad(uHeads, head_texel(idx, 0));
  vec4 h1 = imageLoad(uHeads, head_texel(idx, 1));
  Stroke cur;
  cur.count = min(int(h1.x + 0.5), MAX_VERTS);
  if (cur.count < 2) {
    return;
  }
  for (int k = 0; k < MAX_VERTS; ++k) {
    cur.p[k] = (k < cur.count) ? imageLoad(uVerts, vert_texel(idx, k)).xy : vec2(0.0);
  }
  cur.radius = h1.w;
  float opacity = h0.a;

  /* Eg belongs to the footprint, so it is measured once per iteration. */
  Probe base = probe(cur, h0.rgb);
  float eg = base.eg;
  Stroke best = cur;
  vec3 best_col = h0.rgb;
  float best_score = score(base.em, base.area, eg);
  float best_em = base.em;
  bool changed = false;

  /* Recolour: the covered source mean is the least-squares optimum. */
  Probe rc = probe(cur, base.mean);
  float rc_score = score(rc.em, rc.area, eg);
  if (rc_score < best_score) {
    best_score = rc_score;
    best_col = base.mean;
    best_em = rc.em;
    changed = true;
  }

  float amp = RELAX_MOVE * exp(-0.25 * uRelax.x);
  int candidates = int(clamp(RELAX_CANDS, 1.0, 16.0));
  for (int c = 0; c < candidates; ++c) {
    uint h = hash_u(uint(idx) * 9781u ^ uint(uRelax.x) * 6151u ^ uint(c + 1) * 2654435761u);
    Stroke t = perturb(cur, h, amp);
    /* Try the move with the colour so far and with its own optimum, so a
     * move is not rejected only because the old colour no longer suits. */
    Probe pa = probe(t, best_col);
    float sa = score(pa.em, pa.area, eg);
    Probe pb = probe(t, pa.mean);
    float sb = score(pb.em, pb.area, eg);
    float s_best = sa;
    vec3 c_best = best_col;
    float e_best = pa.em;
    if (sb < sa) {
      s_best = sb;
      c_best = pa.mean;
      e_best = pb.em;
    }
    if (s_best < best_score) {
      best_score = s_best;
      best = t;
      best_col = c_best;
      best_em = e_best;
      changed = true;
    }
  }

  /* Removal: a stroke that fits worse than the ground earns no area. */
  if (RELAX_REMOVE > 0.0 && (best_em + RELAX_AREA_W) > eg * RELAX_REMOVE) {
    imageStore(uHeads, head_texel(idx, 1), vec4(0.0, h1.y, 1.0, h1.w));
    return;
  }
  if (!changed) {
    return;
  }
  float arc = 0.0;
  for (int k = 0; k < best.count; ++k) {
    if (k > 0) {
      arc += distance(best.p[k], best.p[k - 1]);
    }
    imageStore(uVerts, vert_texel(idx, k), vec4(best.p[k], arc, 0.0));
  }
  imageStore(uHeads, head_texel(idx, 0), vec4(best_col, opacity));
  imageStore(uHeads, head_texel(idx, 1), vec4(float(best.count), h1.y, max(arc, 1e-6), best.radius));
}
