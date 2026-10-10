#pragma once
// Compact, binary-safe handoff from Minecraft/Fabric on the Windows host to
// the *native* BOTW Switch NVN renderer via Ryujinx's virtual SD card.
//
// This file deliberately contains no game addresses, hooks or Nintendo assets.
// Host produces the file atomically. Guest validates it before any GPU draw.
#include <cstddef>
#include <cstdint>

namespace BotwCraftMesh {
constexpr uint32_t kMagic = 0x31435742; // "BWC1" little endian
constexpr uint32_t kVersion = 1;
constexpr uint32_t kMaxVertices = 512; // bounded by native guest static arena
struct Header {
    uint32_t magic;
    uint32_t version;
    uint32_t frameId;
    uint32_t vertexCount;
    uint32_t payloadHash; // FNV-1a of vertex bytes
    uint32_t reserved[3];
};
struct Vertex {
    float x, y, z, w;       // projected clip coordinates; not Zelda world coords
    float nx, ny, nz, nw;   // Minecraft flat face normal
};
static_assert(sizeof(Header) == 32);
static_assert(sizeof(Vertex) == 32);
constexpr uint32_t kMaxBytes = sizeof(Header) + kMaxVertices * sizeof(Vertex);

inline uint32_t Hash(const void* source, std::size_t size) {
    const auto* data = static_cast<const uint8_t*>(source);
    uint32_t result = 2166136261u;
    for (std::size_t i = 0; i < size; ++i) {
        result = (result ^ data[i]) * 16777619u;
    }
    return result;
}

inline bool Valid(const void* bytes, std::size_t length) {
    if (!bytes || length < sizeof(Header) || length > kMaxBytes) return false;
    const auto* h = static_cast<const Header*>(bytes);
    if (h->magic != kMagic || h->version != kVersion) return false;
    if (h->vertexCount > kMaxVertices || h->vertexCount % 3 != 0) return false;
    const std::size_t count = std::size_t(h->vertexCount) * sizeof(Vertex);
    if (length != sizeof(Header) + count) return false;
    const auto* payload = static_cast<const uint8_t*>(bytes) + sizeof(Header);
    if (Hash(payload, count) != h->payloadHash) return false;
    const auto* verts = reinterpret_cast<const Vertex*>(payload);
    for (uint32_t i = 0; i < h->vertexCount; ++i) {
        const Vertex& v = verts[i];
        // No NaN, infinity or wildly invalid clip-space memory contents.
        if (!(v.x == v.x && v.y == v.y && v.z == v.z && v.w == v.w)) return false;
        if (v.w <= 0 || v.w > 1000) return false;
        if (v.x < -10000 || v.x > 10000 ||
            v.y < -10000 || v.y > 10000 ||
            v.z < -10000 || v.z > 10000) return false;
    }
    return true;
}
} // namespace BotwCraftMesh
