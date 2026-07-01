/**
 * codec_wrapper.cpp — Emscripten WASM wrapper for codec-share
 *
 * Instance-based design (inspired by BufferShare/Android JNI):
 *   - createEncoder(id) / createDecoder(id)
 *   - encSet(id, data, len) → count
 *   - encGet(id) → frame at a time
 *   - decSet(id, frame) → 0=need more, 1=done, -1=error
 *   - decGet(id) → decoded buffer (stores dataLen per instance)
 *
 * Avoids global-state collision between encoder/decoder
 * and eliminates the need for transport-level dataLen.
 */
#include <emscripten.h>
#include <vector>
#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <memory>
#include <random>

#include "include/decoder.hpp"
#include "include/token.hpp"
#include "include/stream.hpp"

using namespace share::codec;
using Buffer = std::vector<uint8_t>;

/* ── Per-instance state ────────────────────────────────── */

struct EncoderState {
    std::unique_ptr<istream<Buffer>> is;
    std::vector<Buffer>             frames;
    size_t                          pos{0};
    int                             dataLen{0};
};

struct DecoderState {
    std::unique_ptr<decoder<Buffer>> dec;
    int                              capacity{0};
    int                              dataLen{0};  /* set when encode-side feeds it */
};

static std::unordered_map<int, EncoderState> g_encoders;
static std::unordered_map<int, DecoderState> g_decoders;
static std::string                           g_last_error;
static int                                   g_next_handle{1};

static token::shared::Stamp make_token(uint32_t lo, uint32_t hi,
                                       token::Type type = token::Type::MESSAGE) {
    uint64_t seed = (uint64_t(hi) << 32) | lo;
    if (seed == 0) return token::get(type);
    return token::generate(type, seed);
}

extern "C" {

/* ─── Instance management ───────────────────────────── */

EMSCRIPTEN_KEEPALIVE int create_encoder() { return g_next_handle++; }
EMSCRIPTEN_KEEPALIVE int create_decoder() { return g_next_handle++; }

EMSCRIPTEN_KEEPALIVE void destroy_encoder(int id) { g_encoders.erase(id); }
EMSCRIPTEN_KEEPALIVE void destroy_decoder(int id) { g_decoders.erase(id); }

/* ─── Encoder ────────────────────────────────────────── */

/**
 * enc_set(id, data, len, token_lo, token_hi, frame_size) → frame count
 */
EMSCRIPTEN_KEEPALIVE int enc_set(int id, const uint8_t* data, int len,
                                 uint32_t token_lo, uint32_t token_hi,
                                 int frame_size) {
    try {
        auto& es = g_encoders[id];
        es = EncoderState{};
        es.dataLen = len;

        auto token = make_token(token_lo, token_hi);
        es.is = std::make_unique<istream<Buffer>>(token);
        Buffer input(data, data + len);
        size_t count = es.is->set(input, static_cast<uint32_t>(frame_size));
        size_t total = count * 2 + 3;
        for (size_t i = 0; i < total; ++i)
            es.frames.push_back(es.is->pop());
        return static_cast<int>(es.frames.size());
    } catch (const std::exception& e) {
        g_last_error = e.what();
        return 0;
    }
}

/**
 * enc_get(id, out_len) → pointer to next frame, advances
 */
EMSCRIPTEN_KEEPALIVE const uint8_t* enc_get(int id, int* out_len) {
    auto it = g_encoders.find(id);
    if (it == g_encoders.end()) { *out_len = 0; return nullptr; }
    auto& es = it->second;
    if (es.pos >= es.frames.size()) { *out_len = 0; return nullptr; }
    auto& f = es.frames[es.pos++];
    *out_len = static_cast<int>(f.size());
    return f.data();
}

/**
 * enc_reset(id) — clear encoder state for reuse
 */
EMSCRIPTEN_KEEPALIVE void enc_reset(int id) {
    auto it = g_encoders.find(id);
    if (it != g_encoders.end()) g_encoders.erase(it);
}

/* ─── Decoder ────────────────────────────────────────── */

/**
 * dec_create(id, capacity, dataLen, token_lo, token_hi) → 0/1
 *
 * capacity = K (source blocks). dataLen = original data length
 * (from encoder instance). Call once before feeding frames.
 */
EMSCRIPTEN_KEEPALIVE int dec_create(int id, int capacity,
                                    int dataLen,
                                    uint32_t token_lo, uint32_t token_hi) {
    try {
        auto token = make_token(token_lo, token_hi);
        auto& ds = g_decoders[id];
        ds.capacity = capacity > 0 ? capacity : 1;
        ds.dataLen  = dataLen > 0 ? dataLen : 0;
        ds.dec = std::make_unique<decoder<Buffer>>(
            static_cast<size_t>(ds.capacity), token);
        return 1;
    } catch (const std::exception& e) {
        g_last_error = e.what();
        return 0;
    }
}

/**
 * dec_set(id, data, len) → 0=need more, 1=done, -1=error
 *
 * Feed one coded frame. Returns 1 when decoder has enough frames
 * and can produce decoded data.
 */
EMSCRIPTEN_KEEPALIVE int dec_set(int id, const uint8_t* data, int len) {
    auto it = g_decoders.find(id);
    if (it == g_decoders.end()) { g_last_error = "decoder not found"; return -1; }
    auto& ds = it->second;
    if (!ds.dec) { g_last_error = "decoder not initialized"; return -1; }
    try {
        Buffer frame(data, data + len);
        ds.dec->push(std::move(frame));
        return (ds.dec->size() >= static_cast<size_t>(ds.capacity)) ? 1 : 0;
    } catch (const std::exception& e) {
        g_last_error = std::string("dec_set: ") + e.what();
        return -1;
    }
}

/**
 * dec_get(id, out_len) → decoded buffer or nullptr
 *
 * Call only after dec_set() returned 1.
 * Uses per-instance dataLen to bypass GF-corrupted header.
 */
EMSCRIPTEN_KEEPALIVE uint8_t* dec_get(int id, int* out_len) {
    *out_len = 0;
    auto it = g_decoders.find(id);
    if (it == g_decoders.end()) { g_last_error = "decoder not found"; return nullptr; }
    auto& ds = it->second;

    try {
        if (!ds.dec || ds.dec->size() == 0) {
            g_last_error = "no solved blocks";
            return nullptr;
        }

        auto len = static_cast<size_t>(ds.dataLen > 0 ? ds.dataLen : 0);
        if (len == 0) { g_last_error = "zero data length"; return nullptr; }

        auto* out = (uint8_t*)malloc(len);
        if (!out) return nullptr;
        auto* outp = out;
        size_t remaining = len;

        auto bit = ds.dec->begin();
        auto eit = ds.dec->end();

        /* First block: skip 4-byte header (GF-corrupted by unification) */
        if (bit != eit) {
            auto& first = *bit;
            auto skip = std::min(first.size(), size_t(4));
            auto avail = first.size() - skip;
            auto n = std::min(avail, remaining);
            std::copy(first.begin() + static_cast<ptrdiff_t>(skip),
                      first.begin() + static_cast<ptrdiff_t>(skip + n), outp);
            outp += n;
            remaining -= n;
            ++bit;
        }

        /* Remaining blocks: all bytes are data */
        for (; bit != eit && remaining > 0; ++bit) {
            auto n = std::min(bit->size(), remaining);
            std::copy(bit->begin(), bit->begin() + static_cast<ptrdiff_t>(n), outp);
            outp += n;
            remaining -= n;
        }

        *out_len = static_cast<int>(outp - out);
        ds.dec->pop(); /* clear decoder */
        return out;
    } catch (const std::exception& e) {
        g_last_error = std::string("dec_get: ") + e.what();
        *out_len = 0;
        return nullptr;
    }
}

/**
 * dec_reset(id) — clear decoder state for reuse
 */
EMSCRIPTEN_KEEPALIVE void dec_reset(int id) {
    auto it = g_decoders.find(id);
    if (it != g_decoders.end()) g_decoders.erase(it);
}

/* ─── Utilities ──────────────────────────────────────── */

EMSCRIPTEN_KEEPALIVE void mem_free(uint8_t* ptr) { free(ptr); }
EMSCRIPTEN_KEEPALIVE const char* last_error() { return g_last_error.c_str(); }
EMSCRIPTEN_KEEPALIVE int         ping()       { return 42; }

} /* extern "C" */
