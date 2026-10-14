void brushkitBrushModel() {
#ifdef SCENE_STROKE
    // Paintify Scene: hidden behind a nearer surface of the G-buffer.
    if (vDepth > texelFetch(uGDepth, ivec2(gl_FragCoord.xy), 0).r + vDepthTol) discard;
#endif
    // per-layer brush role
    vec4 LA = layerA(), LB = layerB();
    float impasto = ST_IMPASTO * LA.x;
    float dryout = clamp(ST_DRYOUT + LA.y, 0.0, 1.0);
    float edgeSoft = max(ST_EDGE_SOFT * LA.z, 0.3);
    float dryTooth = clamp(ST_DRYTOOTH + LB.w, 0.0, 1.0);

    float hw = max(vHw, 0.3);
    float W = 2.0 * max(vRadius * ST_WIDTH_SCALE * LB.x, 0.3);
    float L = max(vTotalLen, 1e-3);
    float v = vNorm;
    float d = v * hw;                                  // signed px across
    float spc = clamp(vArcPx, 0.0, L);
    float u = spc / L;
    uint s = uint(vTexHash + 0.5) * 2654435761u + 0x9e37u;
    vec2 off = vec2(float(uint(vTexHash + 0.5) & 1023u), float((uint(vTexHash + 0.5) >> 5) & 1023u)) * 0.731;

    // --- bristle comb across the brush ------------------------------------
    float B = ST_BRISTLES;
    float dens = 1.0, shade = 0.0, jag = 0.5;
    vec3 cj = vec3(0.0);
    if (B > 0.5) {
        float x = (clamp(v, -1.3, 1.3) * 0.5 + 0.5) * B;
        float n1 = vnoise(vec2(x, 0.37), s);
        float n2 = vnoise(vec2(x * 0.37 + 11.0, 0.73), s + 7u);
        dens = clamp(1.0 - ST_CLUMP * (0.5 - 0.5 * n2) * 1.3 + 0.2 * n1, 0.0, 1.25);
        shade = vnoise(vec2(x, 5.1), s + 3u);
        jag = 0.5 + 0.5 * vnoise(vec2(x, 21.0), s + 5u);
        cj = vec3(vnoise(vec2(x, 9.0), s + 11u), vnoise(vec2(x, 13.0), s + 13u),
                  vnoise(vec2(x, 17.0), s + 17u));
    }

    // --- shape: body, caps, ragged edges -----------------------------------
    float capFrac = ST_CAP_FRAC;
    bool square = false;
    int tip = int(ST_TIP + 0.5);
    if (capFrac < 0.0) {
        if (tip == 1)      { capFrac = 0.08; square = true; }   // flat
        else if (tip == 2)   capFrac = 0.75;                     // filbert
        else if (tip == 4) { capFrac = 0.03; square = true; }    // knife
        else if (tip == 5) { capFrac = 0.15; square = true; }    // fan
        else                 capFrac = 1.0;                      // round, rigger
    } else {
        square = (tip == 1 || tip == 4 || tip == 5);
    }
    float over = max(-vArcPx, vArcPx - L);
    bool beyond = over > 0.0;
    float jagAmt = ST_END_JAG * (jag - 0.5) * (square ? 1.0 : 0.5);
    float capLen = hw * max(capFrac + jagAmt, 0.04);
    float on = beyond ? over / capLen : 0.0;
    float av = abs(v);
    float q = beyond ? (square ? max(av, on) : sqrt(av * av + on * on)) : av;
    if (ST_EDGE_ROUGH > 0.0) {
        float side = (v >= 0.0) ? 1.0 : -1.0;
        float er = 0.7 * gnoise(vec2(spc / (W * 0.9) + off.x, side * 3.1 + off.y), s + 31u)
                 + 0.3 * gnoise(vec2(spc / (W * 0.22) + off.x * 1.3, side * 5.7 + off.y), s + 37u);
        q -= ST_EDGE_ROUGH * er;
    }
    float shape = clamp((1.0 - q) * hw / edgeSoft + 0.5, 0.0, 1.0) * clamp(vVis, 0.0, 1.0);
    // Geometric coverage for Paintify Scene: the round-capped ribbon, whatever
    // the tip. A flat or knife tip ends at the seed point and would leave it,
    // the cell's highest error, uncovered, so the same stroke would be seeded
    // again every frame.
    float round_d = sqrt(av * av * hw * hw + over * over * float(beyond));
    float covered = clamp(hw - round_d + 0.5, 0.0, 1.0) * clamp(vVis, 0.0, 1.0);
    if (shape < 0.003) {
#ifdef SCENE_STROKE
        if (covered >= 0.003) {
            fragColor = vec4(0.0);
            fragHeight = vec4(0.0, covered, 0.0, 0.0);
            return;
        }
#endif
        discard;
    }

    // --- paint: bristles, load, dry brush ----------------------------------
    float loadU = clamp(ST_LOAD * (1.0 - dryout * pow(u, 1.3)), 0.0, 1.0);
    float streak = (ST_STREAK > 0.0)
        ? gnoise(vec2(spc / (W * ST_STREAK_LEN) + off.x * 0.7, v * max(B, 4.0) * 0.3 + off.y * 0.7), s + 41u)
        : 0.0;
    float tex = 1.0 - ST_BALPHA * (1.0 - clamp(dens, 0.0, 1.0));
    if (ST_STREAK > 0.0) tex *= clamp(1.0 + ST_STREAK * streak, 0.0, 1.0);
    if (dryTooth > 0.0 || ST_LOAD < 0.999 || dryout > 0.0) {
        float tooth = texelFetch(uTooth, ivec2(gl_FragCoord.xy), 0).r;
        float req = (1.0 - loadU) + dryTooth * (0.55 - tooth);
        float val = 0.6 * clamp(dens, 0.0, 1.2) + 0.2 + 0.2 * streak;
        tex *= smoothstep(req - 0.12, req + 0.12, val);
    }
    float alphaT = shape * tex;
    float a = min(1.0, alphaT * vOpacity);
    if (alphaT < 0.002) {
#ifdef SCENE_STROKE
        // Too faint to paint, but this surface is covered: record it, or
        // Paintify Scene would seed a new stroke here every frame.
        fragColor = vec4(0.0);
        fragHeight = vec4(0.0, covered, 0.0, 0.0);
        return;
#else
        discard;
#endif
    }

    // --- colour ------------------------------------------------------------
    vec3 col = vColor;
    col *= 1.0 + ST_BCONTRAST * 0.5 * shade;
    col += ST_CJITTER * cj;
    float groove = 0.0;
    if (ST_GROOVE > 0.0 || ST_GROOVE_COLOR > 0.0) {
        // fine combed lines left by individual bristles, stretched along the stroke
        groove = gnoise(vec2(d / max(ST_GROOVE_PX, 0.5) + off.x * 0.37, spc / (W * 1.4) + off.y * 0.41), s + 53u);
        col *= 1.0 + ST_GROOVE_COLOR * groove;
    }
    if (ST_PICKUP > 0.0) {
        vec3 under = texelFetch(uSnap, ivec2(gl_FragCoord.xy), 0).rgb;
        col = mix(col, under, ST_PICKUP * (0.3 + 0.7 * u));
    }
    if (ST_SMEAR > 0.0) {
        vec2 t = normalize(vTang + vec2(1e-6));
        vec3 dragged = texture(uSnap, (gl_FragCoord.xy - t * ST_SMEAR_LEN * W) / IMG_SIZE).rgb;
        col = mix(col, dragged, ST_SMEAR * (1.0 - 0.4 * u));
    }
    col = clamp(col, 0.0, 1.0);
    fragColor = vec4(col * a, a);            // premultiplied

    // --- relief ------------------------------------------------------------
    float dep = 0.0;
    if (impasto > 0.0) {
        float ridge = (1.0 - ST_RIDGE) * (0.55 + 0.45 * clamp(dens, 0.0, 1.2))
                    + ST_RIDGE * exp(-pow((av - 0.8) / 0.22, 2.0));
        ridge += ST_GROOVE * 0.5 * groove;
        float blob = 1.0 + ST_START_BLOB * exp(-u * L / (W * 0.8));
        dep = impasto * max(ridge, 0.0) * blob * (0.35 + 0.65 * loadU) * smoothstep(0.0, 1.0, shape);
    }
    // r: relief; g: plain coverage, which Paintify Scene reads to find
    // surface no stroke covers yet; a: how much this stroke flattens relief.
    fragHeight = vec4(dep * alphaT, covered, 0.0, clamp(ST_FLATTEN * alphaT, 0.0, 1.0));
}
