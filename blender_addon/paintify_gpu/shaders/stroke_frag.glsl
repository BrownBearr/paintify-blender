/* Coverage and brush texture for one stroke fragment. Colour blends as
 * premultiplied source-over; height goes out with zero alpha, which turns the
 * same blend into the additive `heightBuf += coverage * impasto`. */
#define BRUSH_TILE_W 64
#define BRUSH_TILE_H 48

/* Bilinear tile lookup: wraps along the stroke, clamps across it. */
float brush_sample(float tu, float row, int tile)
{
  float bx = tu * float(BRUSH_TILE_W) - 0.5;
  float x0 = floor(bx);
  float fx = bx - x0;
  int ix0 = int(x0 - float(BRUSH_TILE_W) * floor(x0 / float(BRUSH_TILE_W)));
  int ix1 = (ix0 + 1) % BRUSH_TILE_W;
  int iy0 = clamp(int(floor(row)), 0, BRUSH_TILE_H - 1);
  float fy = row - float(iy0);
  int iy1 = min(iy0 + 1, BRUSH_TILE_H - 1);
  int base = tile * BRUSH_TILE_H;
  float a = texelFetch(uBrush, ivec2(ix0, base + iy0), 0).r;
  float b = texelFetch(uBrush, ivec2(ix1, base + iy0), 0).r;
  float c = texelFetch(uBrush, ivec2(ix0, base + iy1), 0).r;
  float d = texelFetch(uBrush, ivec2(ix1, base + iy1), 0).r;
  return mix(mix(a, b, fx), mix(c, d, fx), fy);
}

void main()
{
  /* worker.js coverage `rEff - dist + 0.5`, with round caps past the ends. */
  float perp = abs(vNorm) * vREff;
  float over = max(0.0, max(-vArcPx, vArcPx - vTotalLen));
  float dist = sqrt(perp * perp + over * over);
  float cov = clamp(vREff - dist + 0.5, 0.0, 1.0);
  if (cov <= 0.0) {
    discard;
  }

  /* uTex: (rows in use, first tile of this layer, u scale, unused). One tile
   * repeat every max(16, 4 * radius) px, as renderStrokeSolid does. */
  if (TEX_STRENGTH > 0.0) {
    int variant = int(vTexHash + 0.5);
    float u_off = float((variant / 8) % 64);
    int tile = int(uTex.y + 0.5) + variant % 8;
    float rows = max(uTex.x, 2.0);
    float tu = fract((vArcPx * uTex.z + u_off) / float(BRUSH_TILE_W));
    float row = clamp(vNorm * 0.5 + 0.5, 0.0, 1.0) * (rows - 1.0);
    cov *= (1.0 - TEX_STRENGTH) + TEX_STRENGTH * brush_sample(tu, row, tile);
  }

  /* Dry brush: worker.js's per-segment fade, applied continuously. */
  float op = vOpacity;
  if (DRY_BRUSH > 0.0) {
    op *= max(0.0, 1.0 - DRY_BRUSH * clamp(vArcPx / max(vTotalLen, 1e-6), 0.0, 1.0));
  }
  float a = min(1.0, cov * op);
  if (a < 0.002 && IMPASTO_STR <= 0.0) {
    discard;
  }
  fragColor = vec4(vColor * a, a);
  fragHeight = vec4(cov * IMPASTO_STR, 0.0, 0.0, 0.0);
}
