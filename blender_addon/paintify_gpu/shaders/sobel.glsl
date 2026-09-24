/* worker.js `computeGradients` on the layer's reference blur: raw Sobel sums
 * (gx, gy, magnitude). Not normalised, because the curvature blend weighs the
 * gradient's magnitude against the unit previous direction. */
float gray(ivec2 p)
{
  return dot(texelFetch(uRef, clamp(p, ivec2(0), uSize - ivec2(1)), 0).rgb,
             vec3(0.299, 0.587, 0.114));
}

void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  float tl = gray(px + ivec2(-1, -1)), tc = gray(px + ivec2(0, -1));
  float tr = gray(px + ivec2(1, -1)), ml = gray(px + ivec2(-1, 0));
  float mr = gray(px + ivec2(1, 0)), bl = gray(px + ivec2(-1, 1));
  float bc = gray(px + ivec2(0, 1)), br = gray(px + ivec2(1, 1));
  float gx = -tl + tr - 2.0 * ml + 2.0 * mr - bl + br;
  float gy = -tl - 2.0 * tc - tr + bl + 2.0 * bc + br;
  imageStore(uOut, px, vec4(gx, gy, sqrt(gx * gx + gy * gy), 0.0));
}
