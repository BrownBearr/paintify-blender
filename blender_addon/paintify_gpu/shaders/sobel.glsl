/* worker.js `computeGradients` on the layer's reference blur: raw Sobel sums
 * (gx, gy, magnitude). Not normalised, because the curvature blend weighs the
 * gradient's magnitude against the unit previous direction.
 *
 * With uMasked, a neighbour on another G-buffer slot reads as the centre, so
 * an object's silhouette steers no stroke on the surface behind it. */
float gray(ivec2 p, ivec2 centre)
{
  ivec2 q = clamp(p, ivec2(0), uSize - ivec2(1));
  if (uMasked != 0 && abs(texelFetch(uMask, q, 0).w - texelFetch(uMask, centre, 0).w) > 0.5) {
    q = centre;
  }
  return dot(texelFetch(uRef, q, 0).rgb, vec3(0.299, 0.587, 0.114));
}

void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  float tl = gray(px + ivec2(-1, -1), px), tc = gray(px + ivec2(0, -1), px);
  float tr = gray(px + ivec2(1, -1), px), ml = gray(px + ivec2(-1, 0), px);
  float mr = gray(px + ivec2(1, 0), px), bl = gray(px + ivec2(-1, 1), px);
  float bc = gray(px + ivec2(0, 1), px), br = gray(px + ivec2(1, 1), px);
  float gx = -tl + tr - 2.0 * ml + 2.0 * mr - bl + br;
  float gy = -tl - 2.0 * tc - tr + bl + 2.0 * bc + br;
  imageStore(uOut, px, vec4(gx, gy, sqrt(gx * gx + gy * gy), 0.0));
}
