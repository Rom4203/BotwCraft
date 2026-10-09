// Host test of native game API startup. NO Nintendo code/data needed.
// Simulates WiiXLaunch's generated import surface to prove fail-closed logic.
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

static bool g_position_supported = false;
static bool g_register_succeeds = true;
static bool g_input_supported = false;
static int g_init_calls = 0;
static int g_tick_registrations = 0;
static void (*g_tick)() = nullptr;
static std::vector<std::string> g_logs;

extern "C" {
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
    // BOTW Switch v1.0.0 currently exposes no valid player API.
    WiiXLaunch_ModEntry();
    assert(Contains("BOTW_NATIVE_UNSUPPORTED"));
    assert(g_init_calls == 0);
    assert(g_tick_registrations == 0);
    assert(g_tick == nullptr);
    // Future version where exact player offsets have been established:
    g_logs.clear();
    g_position_supported = true;
    WiiXLaunch_ModEntry();
    assert(g_init_calls == 1);
    assert(g_tick_registrations == 1);
    assert(g_tick != nullptr);
    for (int i=0; i<6; i++) g_tick();
    assert(Contains("NATIVE_POSITION_MILLI x=4250 y=12000 z=-3500"));
    return 0;
}
