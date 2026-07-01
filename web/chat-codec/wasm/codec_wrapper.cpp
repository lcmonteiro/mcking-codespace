/**
 * codec_wrapper.cpp — Emscripten WASM wrapper for codec-share
 *
 * Uses direct decoder<Buffer> access to avoid header corruption
 * from Gaussian elimination unification. The data length is passed
 * from encoder to decoder directly instead of reading from the
 * (potentially GF-multiplied) header in the first solved block.
 */
#include <emscripten.h>
#include <vector>
#include <cstdint>
#include <cstring>
#include <string>
#include <memory>
#include <random>

#include "include/decoder.hpp"
#include "include/token.hpp"
#include "include/stream.hpp"

using namespace share::codec;
using Buffer = std::vector<uint8_t>;

static std::unique_ptr<istream<Buffer>> g_is;
static std::unique_ptr<decoder<Buffer>> g_dec;
static std::vector<Buffer>              g_encoded;
static size_t                           g_enc_pos{0};
static size_t                           g_dec_capacity{0};
static int                              g_orig_data_len{0};
static std::string                      g_last_error;

static token::shared::Stamp make_token(uint32_t lo, uint32_t hi,
                                       token::Type type = token::Type::MESSAGE) {
    uint64_t seed = (uint64_t(hi) << 32) | lo;
    if (seed == 0) return token::get(type);
    return token::generate(type, seed);
}

extern "C" {

/* Forward declarations */
EMSCRIPTEN_KEEPALIVE uint8_t* dec_get_ex(int* out_len, int data_len);

EMSCRIPTEN_KEEPALIVE int enc_begin(const uint8_t* data, int len,
                                   uint32_t token_lo, uint32_t token_hi,
                                   int frame_size) {
    try {
        g_encoded.clear();
        g_enc_pos = 0;
        g_orig_data_len = len;
        auto token = make_token(token_lo, token_hi);
        g_is = std::make_unique<istream<Buffer>>(token);
        Buffer input(data, data + len);
        size_t count = g_is->set(input, static_cast<uint32_t>(frame_size));
        size_t total = count * 2 + 3;
        for (size_t i = 0; i < total; ++i)
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

EMSCRIPTEN_KEEPALIVE int dec_create(int capacity,
                                    uint32_t token_lo, uint32_t token_hi) {
    try {
        auto token = make_token(token_lo, token_hi);
        g_dec_capacity = static_cast<size_t>(capacity > 0 ? capacity : 1);
        g_dec = std::make_unique<decoder<Buffer>>(g_dec_capacity, token);
        return 1;
    } catch (const std::exception& e) {
        g_last_error = e.what();
        return 0;
    }
}

EMSCRIPTEN_KEEPALIVE int dec_feed(const uint8_t* data, int len) {
    if (!g_dec) { g_last_error = "decoder not initialized"; return -1; }
    try {
        Buffer frame(data, data + len);
        g_dec->push(std::move(frame));
        return (g_dec->size() >= g_dec_capacity) ? 1 : 0;
    } catch (const std::exception& e) {
        g_last_error = std::string("dec_feed: ") + e.what();
        return -1;
    }
}

EMSCRIPTEN_KEEPALIVE uint8_t* dec_get(int* out_len) {
    return dec_get_ex(out_len, g_orig_data_len);
}

EMSCRIPTEN_KEEPALIVE uint8_t* dec_get_ex(int* out_len, int data_len) {
    *out_len = 0;
    if (!g_dec) { g_last_error = "decoder not initialized"; return nullptr; }
    try {
        if (g_dec->size() == 0) { g_last_error = "no solved blocks"; return nullptr; }

        auto len = static_cast<size_t>(data_len > 0 ? data_len : g_orig_data_len);
        if (len == 0) { g_last_error = "zero data length"; return nullptr; }

        auto* out = (uint8_t*)malloc(len);
        if (!out) return nullptr;
        auto* outp = out;
        size_t remaining = len;

        /* Extract from all solved blocks, in pivot order (= source order) */
        auto bit = g_dec->begin();
        auto eit = g_dec->end();

        /* First block: skip 4-byte header */
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
        g_dec->pop(); /* clear decoder */
        return out;
    } catch (const std::exception& e) {
        g_last_error = std::string("dec_get: ") + e.what();
        *out_len = 0;
        return nullptr;
    }
}

EMSCRIPTEN_KEEPALIVE void dec_reset() { g_dec.reset(); g_dec_capacity = 0; }
EMSCRIPTEN_KEEPALIVE void mem_free(uint8_t* ptr) { free(ptr); }
EMSCRIPTEN_KEEPALIVE const char* last_error() { return g_last_error.c_str(); }
EMSCRIPTEN_KEEPALIVE int         ping()       { return 42; }

} /* extern "C" */
