cmake_minimum_required(VERSION 3.20)
project(chat-codec LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── dependencies ─────────────────────────────────────────
# clone codec-share alongside this project:
#   git clone https://github.com/lcmonteiro/codec-share.git ../codec-share
set(CODEC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/wasm/codec-share"
    CACHE PATH "path to codec-share submodule")

# ── WASM binary ──────────────────────────────────────────
set(CMAKE_EXECUTABLE_SUFFIX ".html")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s WASM=1")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s MODULARIZE=1")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s EXPORT_NAME='CodecShare'")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s ALLOW_MEMORY_GROWTH=1")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s FILESYSTEM=0")

# exports
set(EXPORTED_FUNCS
    _enc_begin _enc_next _enc_reset
    _dec_create _dec_feed _dec_ready _dec_get _dec_reset
    _mem_free _last_error _ping
    _malloc _free
)
list(JOIN EXPORTED_FUNCS "," EXPORTED_LIST)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s EXPORTED_FUNCTIONS='[${EXPORTED_LIST}]'")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s EXPORTED_RUNTIME_METHODS='[ccall,getValue,setValue,HEAPU8]'")

add_executable(chat-codec wasm/codec_wrapper.cpp)
target_include_directories(chat-codec PRIVATE "${CODEC_DIR}")
