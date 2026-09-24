/* Frame-constant settings, uploaded once per painted frame. Painter._params in
 * painter.py writes this layout. Per-layer and per-pass values travel as push
 * constants instead, so no uniform buffer is ever rewritten mid-frame. */
#define IMG_SIZE         params.p0.xy
#define THRESHOLD        params.p1.x
#define MAX_STROKE_LEN   params.p1.y
#define MIN_STROKE_LEN   params.p1.z
#define CURVATURE        params.p1.w
#define OPACITY          params.p2.x
#define FRAME_DIFF       params.p2.y
#define JITTER_PER_FRAME params.p2.z
#define FRAME            params.p2.w
#define JITTER_HUE       params.p3.x
#define JITTER_SAT       params.p3.y
#define JITTER_VAL       params.p3.z
#define SIZE_JITTER      params.p3.w
#define ANGLE_JITTER     params.p4.x
#define OPACITY_JITTER   params.p4.y
#define TEX_STRENGTH     params.p4.z
#define TEX_TAPER        params.p4.w
#define IMPASTO_STR      params.p5.x
#define IMPASTO_LIGHT    params.p5.y
#define LIGHT_ANGLE      params.p5.z
#define DRY_BRUSH        params.p5.w
#define RELAX_AREA_W     params.p6.x
#define RELAX_MOVE       params.p6.y
#define RELAX_CANDS      params.p6.z
#define RELAX_REMOVE     params.p6.w

/* Zero unless per-frame jitter is on, so a still repaints identically and a
 * static region of an animation keeps its strokes. */
uint frame_salt()
{
  return (JITTER_PER_FRAME > 0.5) ? uint(FRAME) : 0u;
}
