/* Separable Gaussian, worker.js `gaussianBlurRGB`: radius ceil(2.5 sigma),
 * weights normalised over that window, clamp to edge. uDir.xy is the step
 * and uDir.zw the image size.
 *
 * With uMasked (Paintify Scene), only pixels of the centre's G-buffer slot
 * (uMask.w) take part, so each surface is painted from its own appearance:
 * a floor next to a moving head does not pick up the head's colours. */
#define MAX_BLUR_RADIUS 96

void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  ivec2 size = uDir.zw;
  if (px.x >= size.x || px.y >= size.y) {
    return;
  }
  float sigma = max(0.1, uSigma);
  int radius = min(int(ceil(sigma * 2.5)), MAX_BLUR_RADIUS);
  float inv2s2 = -0.5 / (sigma * sigma);
  vec3 acc = vec3(0.0);
  float wsum = 0.0;
  float slot = (uMasked != 0) ? texelFetch(uMask, px, 0).w : 0.0;
  for (int d = -radius; d <= radius; ++d) {
    float wt = exp(inv2s2 * float(d * d));
    ivec2 q = clamp(px + uDir.xy * d, ivec2(0), size - ivec2(1));
    if (uMasked != 0 && abs(texelFetch(uMask, q, 0).w - slot) > 0.5) {
      continue;
    }
    acc += wt * texelFetch(uIn, q, 0).rgb;
    wsum += wt;
  }
  imageStore(uOut, px, vec4(acc / max(wsum, 1e-8), 1.0));
}
