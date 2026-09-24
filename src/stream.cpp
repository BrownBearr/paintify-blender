// Persistent binary RGBA pipe for Blender. Stdout contains protocol bytes only.
#include <glad/glad.h>
#include <GLFW/glfw3.h>
#include "pipeline.h"
#include "params.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

namespace {
constexpr uint32_t MAGIC = 0x31565050u; // "PPV1" little endian
constexpr uint32_t MAX_PIXELS = 3840u * 2160u;

struct FrameHeader {
    uint32_t magic, width, height, sequence;
    float threshold, curvature, brushTexture, impasto, impastoLight, temporalDiff;
    uint32_t relax, preset;
};
static_assert(sizeof(FrameHeader) == 48, "Pipe header layout changed");

struct ResultHeader { uint32_t magic, width, height, sequence; };
static_assert(sizeof(ResultHeader) == 16, "Pipe response layout changed");

bool readExact(void* dst, size_t bytes) {
    return std::fread(dst, 1, bytes, stdin) == bytes;
}

bool writeExact(const void* src, size_t bytes) {
    return std::fwrite(src, 1, bytes, stdout) == bytes;
}

void preset(uint32_t id, TuningParams& p, RenderConfig& c) {
    // Same values as the original web presets in main.cpp.
    switch (id) {
    case 1: // expressionist
        c.radii = {12.f, 6.f, 3.f};
        p.maxStrokeLength = 28.f; p.minStrokeLength = 8.f;
        p.gridFactor = .9f; p.opacity = .95f;
        p.jitterHue = .15f; p.jitterSat = .20f; p.jitterVal = .15f;
        break;
    case 2: // pointillist
        c.radii = {4.f, 2.f}; c.underpaint = Underpaint::Average;
        p.maxStrokeLength = 3.f; p.minStrokeLength = 1.f;
        p.gridFactor = .75f; p.opacity = .85f;
        p.jitterHue = .10f; p.jitterSat = .15f; p.jitterVal = .10f;
        break;
    case 3: // wash
        c.radii = {20.f, 10.f};
        p.maxStrokeLength = 32.f; p.minStrokeLength = 10.f;
        p.gridFactor = 1.5f; p.opacity = .4f;
        p.jitterHue = .20f; p.jitterSat = .30f; p.jitterVal = .20f;
        break;
    case 4: // detail
        c.radii = {6.f, 3.f, 1.5f};
        p.maxStrokeLength = 10.f; p.minStrokeLength = 4.f;
        p.gridFactor = 1.f; p.opacity = 1.f;
        p.jitterHue = p.jitterSat = p.jitterVal = 0.f;
        break;
    default: break;
    }
}
}

int main() {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (!glfwInit()) { std::fprintf(stderr, "glfwInit failed\n"); return 1; }
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 6);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
    glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE);
    GLFWwindow* window = glfwCreateWindow(64, 64, "Paintify Stream", nullptr, nullptr);
    if (!window) { std::fprintf(stderr, "OpenGL 4.6 required\n"); glfwTerminate(); return 1; }
    glfwMakeContextCurrent(window);
    if (!gladLoadGLLoader((GLADloadproc)glfwGetProcAddress)) return 1;
    Pipeline pipeline;
    if (!pipeline.init()) return 1;

    FrameHeader h{};
    FrameHeader previous{};
    bool havePrevious = false;
    while (readExact(&h, sizeof(h))) {
        if (h.magic != MAGIC || h.width == 0 || h.height == 0 ||
            uint64_t(h.width) * h.height > MAX_PIXELS || h.preset > 4 || h.relax > 12) {
            std::fprintf(stderr, "Invalid viewport frame header\n"); break;
        }
        std::vector<unsigned char> input(size_t(h.width) * h.height * 4);
        if (!readExact(input.data(), input.size())) break;
        TuningParams params;
        RenderConfig config;
        preset(h.preset, params, config);
        params.threshold = std::clamp(h.threshold, 0.f, 255.f);
        params.curvature = std::clamp(h.curvature, 0.f, 1.f);
        params.texStrength = std::clamp(h.brushTexture, 0.f, 1.f);
        params.impastoStrength = std::clamp(h.impasto, 0.f, 1.f);
        params.impastoLight = std::clamp(h.impastoLight, 0.f, 1.f);
        params.frameDiffThreshold = std::clamp(h.temporalDiff, 0.f, 255.f);
        params.frame = float(h.sequence);
        config.relaxIterations = int(h.relax);
        bool sameLook = havePrevious && previous.width == h.width && previous.height == h.height &&
            previous.preset == h.preset && previous.relax == h.relax &&
            previous.threshold == h.threshold && previous.curvature == h.curvature &&
            previous.brushTexture == h.brushTexture && previous.impasto == h.impasto &&
            previous.impastoLight == h.impastoLight && previous.temporalDiff == h.temporalDiff;
        if (!sameLook) pipeline.resetTemporal();
        if (!pipeline.setSource(input.data(), int(h.width), int(h.height))) break;
        pipeline.render(params, config, sameLook && h.temporalDiff > 0.f);
        const auto output = pipeline.readCanvas();
        const ResultHeader response{MAGIC, h.width, h.height, h.sequence};
        if (output.size() != input.size() || !writeExact(&response, sizeof(response)) ||
            !writeExact(output.data(), output.size())) break;
        previous = h;
        havePrevious = true;
    }
    pipeline.shutdown();
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}
