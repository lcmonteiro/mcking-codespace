/* ─── shared/codec-bridge.cjs — CodecBridge class (Node + Browser) ───
 *
 * CommonJS module used by both cli/ and public/.
 * Browser-side: loaded via bundler or wrapped as <script>.
 *
 * Depends on: Emscripten glue (codec_share.js) which must be loaded first.
 *
 * API:
 *   new CodecBridge()
 *   .init()              → async, loads WASM
 *   .encode(text, token) → { frames: [...], capacity, dataLen }
 *   .feed(msgId, frameData, token, capacity, dataLen)
 *   .tryDecode(msgId)    → { text, frameCount } | null
 *   .reset()
 *   ._cleanup()
 */

const path = require('path');
const fs   = require('fs');
const { hashSeed } = require('./hash.js');

/* ── CodecBridge ── */

class CodecBridge {
  constructor(opts) {
    opts = opts || {};
    this.wasmDir    = opts.wasmDir || path.resolve(__dirname, '..', 'public');
    this.module     = null;
    this.ready      = false;
    this._partials  = new Map();
    this._decoded   = new Set();
    this._encHandle = null;
    this._lenPtr    = null;
  }

  async init() {
    if (this.ready) return;

    const wasmJsPath = path.join(this.wasmDir, 'codec_share.js');
    if (!fs.existsSync(wasmJsPath)) {
      throw new Error(
        `codec_share.js not found at ${wasmJsPath}\n` +
        `Run: bash wasm/build.sh  (requires Emscripten)`
      );
    }

    const CodecShare = require(wasmJsPath);

    const wasmBinaryFile = path.join(this.wasmDir, 'codec_share.wasm');
    if (!fs.existsSync(wasmBinaryFile)) {
      throw new Error(
        `codec_share.wasm not found at ${wasmBinaryFile}\n` +
        `Run: bash wasm/build.sh`
      );
    }

    const mod = await CodecShare({
      locateFile: (file) => path.join(this.wasmDir, file),
      onAbort: (msg) => { throw new Error('WASM abort: ' + msg); },
    });

    this.module = mod;
    this._lenPtr = mod._malloc(4);  /* 4 bytes for length output */
    if (!this._lenPtr) throw new Error('_malloc failed (lenPtr)');

    /* Verify exports */
    const required = ['_create_encoder','_destroy_encoder','_enc_set','_enc_get',
                      '_create_decoder','_destroy_decoder','_dec_create','_dec_set','_dec_get',
                      '_malloc','_free','_ping'];
    for (const e of required) {
      if (typeof mod[e] !== 'function') {
        /* Maybe the Module is nested (Emscripten Module object vs factory) */
        if (typeof globalThis[e] === 'function') {
          this.module = globalThis;
          break;
        }
        throw new Error(`WASM missing export: ${e}`);
      }
    }

    /* Ping test */
    const pong = mod._ping();
    if (pong !== 42) throw new Error(`Ping failed: got ${pong}`);

    this.ready = true;
    console.log('[codec-bridge] initialized, ping:', pong);
  }

  _tokenParts(s) {
    const h = hashSeed(String(s));
    return {
      lo: Number(h & 0xFFFFFFFFn) >>> 0,
      hi: Number((h >> 32n) & 0xFFFFFFFFn) >>> 0,
    };
  }

  /* ── Encode ── */

  encode(text, token) {
    if (!this.ready) throw new Error('CodecBridge not initialized');

    const data = Buffer.from(text, 'utf-8');
    const len  = data.length;

    /* Derive seed FNV-1a 64-bit from token */
    const { lo, hi } = this._tokenParts(token);

    /* Create encoder instance */
    const encH = this.module._create_encoder();
    if (encH < 0) throw new Error(`create_encoder failed: ${encH}`);

    this._encHandle = encH;

    /* enc_set returns (capacity, frameCount) packed? Let's call separately */
    /* First: enc_set(handle, dataPtr, dataLen, lo, hi, FS) */
    const dataPtr = this.module._malloc(len);
    if (!dataPtr) throw new Error('_malloc failed (data)');

    /* Copy data to WASM heap */
    this.module.HEAPU8.set(data, dataPtr);

    const count = this.module._enc_set(encH, dataPtr, len, lo, hi, 64);
    if (count < 0) {
      this.module._free(dataPtr);
      throw new Error(`enc_set failed: ${count}`);
    }

    /* enc_get: allocate frame buffer (max 64KB) and retrieve frames */
    const fs = 64;  /* Frame Size */
    const frames = [];
    let frameBufPtr = this.module._malloc(fs);
    if (!frameBufPtr) { this.module._free(dataPtr); throw new Error('_malloc failed (frameBuf)'); }

    let capacity = 0;
    while (true) {
      const ret = this.module._enc_get(encH, frameBufPtr, this._lenPtr);
      if (ret < 0) break;  /* no more frames */
      const frameLen = this.module.HEAPU32[this._lenPtr >> 2];
      if (frameLen === 0) break;
      if (capacity === 0) capacity = ret;  /* first call returns capacity */
      const frame = Buffer.from(this.module.HEAPU8.slice(frameBufPtr, frameBufPtr + fs));
      frames.push(frame);
    }

    this.module._free(frameBufPtr);
    this.module._free(dataPtr);

    /* Clean up encoder handle */
    this.module._destroy_encoder(encH);
    this._encHandle = null;

    const dataLen = len;
    console.log('[codec-bridge] encode: len=', dataLen, 'capacity=', capacity,
                'frames=', frames.length);

    return { frames, capacity, dataLen };
  }

  /* ── Feed (incoming frame) ── */

  feed(msgId, frameData, token, capacity, dataLen) {
    if (!this.ready) return;

    /* Dedup: skip already-decoded messages */
    if (this._decoded.has(msgId)) {
      return;
    }

    const key = String(msgId);
    let state = this._partials.get(key);

    if (!state) {
      const h = hashSeed(token);
      const lo = Number(h & 0xFFFFFFFFn);
      const hi = Number((h >> 32n) & 0xFFFFFFFFn);

      /* Create decoder */
      const decH = this.module._create_decoder();
      if (decH < 0) { console.error('[codec-bridge] create_decoder failed'); return; }

      const ret = this.module._dec_create(decH, capacity, dataLen, lo, hi);
      if (ret < 0) {
        console.error('[codec-bridge] dec_create failed:', ret);
        this.module._destroy_decoder(decH);
        return;
      }

      state = {
        handle: decH,
        capacity,
        dataLen,
        frameCount: 0,
        frames: [],
      };
      this._partials.set(key, state);
    }

    /* Copy frame data to WASM heap */
    const ptr = this.module._malloc(frameData.length);
    if (!ptr) { console.error('[codec-bridge] _malloc failed (feed)'); return; }
    this.module.HEAPU8.set(new Uint8Array(frameData), ptr);

    const status = this.module._dec_set(state.handle, ptr, frameData.length);
    this.module._free(ptr);

    state.frameCount++;

    if (status < 0) {
      console.warn('[codec-bridge] dec_set error:', status, 'for msgId', msgId,
                   'frame', state.frameCount);
    }
  }

  /* ── Try decode ── */

  tryDecode(msgId) {
    if (!this.ready) return null;

    const key = String(msgId);
    const state = this._partials.get(key);
    if (!state) return null;

    /* Dedup */
    if (this._decoded.has(msgId)) return null;

    /* Try to get decoded data */
    const outPtr = this.module._malloc(state.dataLen + 4);
    if (!outPtr) { console.error('[codec-bridge] _malloc failed (tryDecode)'); return null; }

    const ret = this.module._dec_get(state.handle, outPtr, this._lenPtr);

    if (ret < 0) {
      /* Not ready yet */
      this.module._free(outPtr);
      return null;
    }

    const outLen = this.module.HEAPU32[this._lenPtr >> 2];
    const dataBuf = Buffer.from(this.module.HEAPU8.slice(outPtr, outPtr + outLen));
    this.module._free(outPtr);

    /* Convert to string */
    const text = dataBuf.toString('utf-8');

    /* Mark decoded */
    this._decoded.add(msgId);
    if (this._decoded.size > 200) {
      const first = this._decoded.values().next().value;
      this._decoded.delete(first);
    }

    /* Clean up decoder */
    this.module._destroy_decoder(state.handle);
    this._partials.delete(key);

    const result = {
      text,
      frameCount: state.frameCount,
    };

    console.log('[codec-bridge] decoded msgId=', msgId, 'len=', outLen,
                'frames=', result.frameCount);

    return result;
  }

  reset() {
    this._partials.clear();
    this._decoded.clear();
    this._encHandle = null;
  }

  _cleanup() {
    this.reset();
    if (this._lenPtr) { try { this.module?._free(this._lenPtr); } catch(_) {} this._lenPtr = null; }
    this.module = null;
    this.ready = false;
  }
}

module.exports = { CodecBridge, hashSeed };
