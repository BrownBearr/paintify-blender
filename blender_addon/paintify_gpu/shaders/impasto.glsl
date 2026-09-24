/* worker.js `applyImpastoLighting`: light the accumulated coverage as a
 * height field and scale the canvas. Relative to flat, so bare canvas keeps
 * its colour. Rows run bottom to top here, hence +sin for the light's y. */
float height_at(ivec2 p)
{
  return texelFetch(uHeight, clamp(p, ivec2(0), uSize - ivec2(1)), 0).r;
}

void main()
{
  ivec2 px = ivec2(gl_GlobalInvocationID.xy);
  if (px.x >= uSize.x || px.y >= uSize.y) {
    return;
  }
  float ang = LIGHT_ANGLE * DEG_TO_RAD;
  vec3 L = normalize(vec3(cos(ang), sin(ang), 0.5));
  float dzdx = (height_at(px + ivec2(1, 0)) - height_at(px - ivec2(1, 0))) * 0.5;
  float dzdy = (height_at(px + ivec2(0, 1)) - height_at(px - ivec2(0, 1))) * 0.5;
  vec3 N = normalize(vec3(-dzdx, -dzdy, 1.0));
  float light = clamp(1.0 + IMPASTO_LIGHT * 2.5 * (dot(N, L) - L.z), 0.35, 1.8);
  vec4 c = imageLoad(uCanvas, px);
  imageStore(uCanvas, px, vec4(min(c.rgb * light, vec3(1.0)), c.a));
}
