/* uSlot.x: the object's slot (1 and up), or -2 for geometry that only hides
 * what is behind it (instances). Background stays at the clear value, -1. */
void main()
{
  gPos = vec4(vLocal, uSlot.x);
  gDepth = vec4(vDepth, 0.0, 0.0, 0.0);
}
