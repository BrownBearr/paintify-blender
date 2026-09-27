/* Paintify Scene's G-buffer: object-space position, object slot and linear
 * view depth of the nearest surface per pixel, drawn with the same camera as
 * the painted image. uViewZ is the z row of the model-view matrix. */
void main()
{
  vec4 p = vec4(pos, 1.0);
  gl_Position = uMVP * p;
  vLocal = pos;
  vDepth = -dot(uViewZ, p);
}
