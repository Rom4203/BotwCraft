// Host test of native game API startup. NO Nintendo code/data needed.
// Simulates WiiXLaunch's generated import surface to prove fail-closed logic.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include "../native_guest_mesh.hpp"

static bool g_position_supported = false;
static bool g_register_succeeds = true;
static bool g_input_supported = false;
static int g_init_calls = 0;
static int g_tick_registrations = 0;
static void (*g_tick)() = nullptr;
static std::vector<std::string> g_logs;
static uint32_t g_native_draw_registrations = 0;
static uint32_t g_draw_calls = 0;
static uint32_t g_draw_vertices = 0;
static void (*g_draw)(uintptr_t, uintptr_t, int32_t, int32_t) = nullptr;
static std::vector<uint8_t> g_file_contents;


extern "C" {
int32_t wiixl_import__wiixl_core__GameReadFile(const char* path, void* out, uint32_t cap) {
    if (!path || std::string(path).find("botwcraft/frame.bin") == std::string::npos)
        return -1;
    if (g_file_contents.empty() || g_file_contents.size() > cap) return -1;
    std::memcpy(out, g_file_contents.data(), g_file_contents.size());
    return static_cast<int32_t>(g_file_contents.size());
}
void wiixl_import__wiixl_core__Log(const char* msg) {
    g_logs.emplace_back(msg ? msg : "");
}
uint32_t wiixl_import__botw_player__SupportsPosition() {
    return g_position_supported ? 1 : 0;
}
uint32_t wiixl_import__botw_player__Init() {
    ++g_init_calls;
    return 1;
}
uint32_t wiixl_import__botw_player__RegisterTick(void (*fn)()) {
    ++g_tick_registrations;
    if (!g_register_succeeds) return 0;
    g_tick = fn;
    return 1;
}
uint32_t wiixl_import__botw_player__GetPosition(float* out) {
    out[0] = 4.25f; out[1] = 12.0f; out[2] = -3.5f;
    return 1;
}
uint32_t wiixl_import__botw_input__SupportsInjection() {
    return g_input_supported ? 1 : 0;
}
uint32_t wiixl_import__botw_gfx__RegisterDraw(
    void (*cb)(uintptr_t, uintptr_t, int32_t, int32_t)) {
    ++g_native_draw_registrations;
    g_draw = cb;
    return 1;
}
uint32_t wiixl_import__botw_gfx__DrawMesh(
    uintptr_t cmdBuf, uintptr_t dst, const float* vertices, uint32_t count) {
    if (cmdBuf && dst && vertices) {
        ++g_draw_calls;
        g_draw_vertices = count;
        return 1;
    }
    return 0;
}
uint32_t wiixl_import__botw_gfx__IsGX2() {
    return 0;
}
}
extern "C" void WiiXLaunch_ModEntry();

static bool Contains(const char* part) {
    for (const auto& line : g_logs) {
        if (line.find(part) != std::string::npos) return true;
    }
    return false;
}

int main() {
    // BOTW Switch 1.5.0 currently exposes no verified Link position API.
    WiiXLaunch_ModEntry();
    assert(Contains("BOTW_NATIVE_UNSUPPORTED"));
    assert(g_init_calls == 0);
    assert(g_tick_registrations == 0);
    assert(g_tick == nullptr);
    assert(g_native_draw_registrations == 1);
    assert(g_draw != nullptr);
    // First game callback sees no frame; must not draw.
    g_draw(1, 1, 1280, 720);
    assert(g_draw_calls == 0);

    BotwCraftMesh::Vertex triangle[3] = {
        {-0.1f, -0.1f, 0.5f, 1.0f, 1.f, 0.f, 0.f, 1.f},
        { 0.1f, -0.1f, 0.5f, 1.0f, 1.f, 0.f, 0.f, 1.f},
        { 0.0f,  0.1f, 0.5f, 1.0f, 1.f, 0.f, 0.f, 1.f},
    };
    BotwCraftMesh::Header header{};
    header.magic = BotwCraftMesh::kMagic;
    header.version = BotwCraftMesh::kVersion;
    header.frameId = 1;
    header.vertexCount = 3;
    header.payloadHash = BotwCraftMesh::Hash(triangle, sizeof(triangle));
    g_file_contents.resize(sizeof(header) + sizeof(triangle));
    std::memcpy(g_file_contents.data(), &header, sizeof(header));
    std::memcpy(g_file_contents.data() + sizeof(header), triangle, sizeof(triangle));
    assert(BotwCraftMesh::Valid(g_file_contents.data(), g_file_contents.size()));
    for (int i = 0; i < 12; ++i) g_draw(1, 1, 1280, 720);
    assert(g_draw_calls > 0);
    assert(g_draw_vertices == 3);
    assert(Contains("BotwCraft:MESH_ROMFS_READ_OK"));
    assert(Contains("BotwCraft:MESH_FRAME_FIRST_ACCEPT"));
    uint32_t priorCalls = g_draw_calls;
    // Corruption is rejected without replacing the previous validated frame.
    g_file_contents.back() ^= 0xff;
    for (int i = 0; i < 12; ++i) g_draw(1, 1, 1280, 720);
    assert(g_draw_calls > priorCalls);
    assert(!BotwCraftMesh::Valid(g_file_contents.data(), g_file_contents.size()));
    g_file_contents.clear();

    // Future version where exact player offsets have been established:
    g_logs.clear();
    g_position_supported = true;
    WiiXLaunch_ModEntry();
    assert(g_native_draw_registrations == 2);
    assert(g_init_calls == 1);
    assert(g_tick_registrations == 1);
    assert(g_tick != nullptr);
    for (int i=0; i<6; i++) g_tick();
    assert(Contains("NATIVE_POSITION_MILLI x=4250 y=12000 z=-3500"));
    return 0;
}
