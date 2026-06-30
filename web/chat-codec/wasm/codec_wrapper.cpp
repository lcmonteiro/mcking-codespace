/**
 * codec_wrapper.cpp — Emscripten WASM wrapper for codec-share
 *
 * Uses codec-share's stream API (istream → ostream).
 *
 * Encode (split + fountain code):
 *   istream.set(data, frameSize) → returns coded frame count
 *   For each: istream.pop() → coded frame
 *
 * Decode (collect + reassemble):
 *   ostream.push(frame) → returns 0 when complete
 *   ostream.get() → original data
 *
 * Token seed passed as two u32 values (lo+hi) for WASM FFI compat.
 */
#include <emscripten.h>
#include <vector>
#include <cstdint>
#include <cstring>
#include <string>
#include <memory>

#include "include/stream.hpp"
#include "include/token.hpp"
#include "include/helpers/copy.hpp"

using namespace share::codec;
using Buffer = std::vector<uint8_t>;

/* ── State ──────────────────────────────────────────────── */
static std::unique_ptr<istream<Buffer>> g_is;
static std::unique_ptr<ostream<Buffer>> g_os;
static std::vector<Buffer>              g_encoded;   /* cached encoded frames */
static size_t                           g_enc_pos{0};
static std::string                      g_last_error;

/* ── Helpers ──────────────────────────────────────────────── */
static token::shared::Stamp make_token(uint32_t lo, uint32_t hi,
                                       token::Type type = token::Type::MESSAGE) {
    uint64_t seed = (uint64_t(hi) << 32) | lo;
    if (seed == 0) return token::get(type);
    return token::generate(type, seed);
}

/* ═══════════════════════════════════════════════════════════
   EXPORTED C API
   ═══════════════════════════════════════════════════════════ */

extern "C" {

/* ── Encode ─────────────────────────────────────────────────
 * Split a flat message into coded frames. Each frame is
 * self‑contained and can be decoded independently.
 *
 * enc_begin(data, len, token_lo, token_hi, frame_size)
 *   → number of coded frames (0 = error)
 *
 * Call enc_next() repeatedly to get each frame. */
EMSCRIPTEN_KEEPALIVE int enc_begin(const uint8_t* data, int len,
                                   uint32_t token_lo, uint32_t token_hi,
                                   int frame_size) {
    try {
        g_encoded.clear();
        g_enc_pos = 0;

        auto token = make_token(token_lo, token_hi);
        g_is = std::make_unique<istream<Buffer>>(token);

        Buffer input(data, data + len);
        size_t count = g_is->set(input, static_cast<uint32_t>(frame_size));

        for (size_t i = 0; i < count; ++i)
            g_encoded.push_back(g_is->pop());

        return static_cast<int>(g_encoded.size());
    } catch (const std::exception& e) {
        g_last_error = e.what();
        return 0;
    }
}

EMSCRIPTEN_KEEPALIVE const uint8_t* enc_next(int* out_len) {
    if (g_enc_pos >= g_encoded.size()) { *out_len = 0; return nullptr; }
    auto& f = g_encoded[g_enc_pos++];
    *out_len = static_cast<int>(f.size());
    return f.data();
}

EMSCRIPTEN_KEEPALIVE void enc_reset() {
    g_is.reset();
    g_encoded.clear();
    g_enc_pos = 0;
}

/* ── Decode ─────────────────────────────────────────────────
 * Feed coded frames one at a time into an ostream.
 * When push returns non‑zero, data is ready.
 *
 * dec_create(token_lo, token_hi)
 * dec_feed(frame, len) → 1 = decode complete, 0 = need more, -1 = error
 * dec_ready() → 1 if decoded data available
 * dec_get(out_len) → decoded bytes (caller must mem_free) */
EMSCRIPTEN_KEEPALIVE int dec_create(uint32_t token_lo, uint32_t token_hi) {
    try {
        auto token = make_token(token_lo, token_hi);
        g_os = std::make_unique<ostream<Buffer>>(token);
        return 1;
    } catch (const std::exception& e) {
        g_last_error = e.what();
        return 0;
    }
}

EMSCRIPTEN_KEEPALIVE int dec_feed(const uint8_t* data, int len) {
    if (!g_os) { g_last_error = "ostream not initialized"; return -1; }
    try {
        Buffer frame(data, data + len);
        /* push returns 0 when complete, non-zero is total */
        return g_os->push(std::move(frame)) == 0 ? 1 : 0;
    } catch (const std::exception& e) {
        g_last_error = e.what();
        return -1;
    }
}

EMSCRIPTEN_KEEPALIVE int dec_ready() {
    if (!g_os) return 0;
    return g_os->full() ? 1 : 0;
}

EMSCRIPTEN_KEEPALIVE uint8_t* dec_get(int* out_len) {
    if (!g_os || !g_os->full()) { *out_len = 0; return nullptr; }
    try {
        auto result = g_os->get();
        auto* out   = (uint8_t*)malloc(result.size());
        memcpy(out, result.data(), result.size());
        *out_len = static_cast<int>(result.size());
        return out;
    } catch (const std::exception& e) {
        g_last_error = e.what();
        *out_len = 0;
        return nullptr;
    }
}

EMSCRIPTEN_KEEPALIVE void dec_reset() { g_os.reset(); }

/* ── Memory ───────────────────────────────────────────────── */
EMSCRIPTEN_KEEPALIVE void mem_free(uint8_t* ptr) { free(ptr); }

/* ── Info ─────────────────────────────────────────────────── */
EMSCRIPTEN_KEEPALIVE const char* last_error() { return g_last_error.c_str(); }
EMSCRIPTEN_KEEPALIVE int         ping()       { return 42; }

} /* extern "C" */
