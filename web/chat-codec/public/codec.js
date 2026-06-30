/* ─── codec.js — WASM codec-share bridge (no fallback) ────
 *
 * Wraps the Emscripten CodecShare module (istream/ostream API).
 * Requires codec_share.js + codec_share.wasm to be loaded.
 *
 * Encoding:
 *   frames[] = encode(msg, tokenStr)
 *     - splits message into coded frames via istream
 *
 * Decoding:
 *   count = feed(msgId, frame, tokenStr)
 *   bool  = ready(msgId)
 *   str|null = get(msgId)
 *   purge(msgId)
 *
 * Token -> seed: FNV-1a 64-bit -> lo (u32) / hi (u32)
 *   (WASM FFI uses two u32 for uint64_t compat)
 */

class CodecBridge {
  constructor() {
    this.module    = null;
    this.ready     = false;
    this._partials = new Map(); /* key -> { frames: [], lo, hi, capacity } */
  }

  /* ── Init WASM ─────────────────────────────────────── */

  async init() {
    if (this.ready) return;
    if (typeof CodecShare === 'undefined') {
      throw new Error(
        'CodecShare WASM module not loaded. ' +
        'Ensure codec_share.js script is included before app.js.'
      );
    }
    return new Promise((resolve, reject) => {
      CodecShare({
        onRuntimeInitialized: () => {
          this.module = CodecShare;
          this.ready  = true;
          console.log('[codec] WASM ready, ping:', CodecShare._ping());
          resolve();
        },
        onAbort: (msg) => {
          reject(new Error('WASM abort: ' + msg));
        },
      });
    });
  }

  /* ── Helpers ───────────────────────────────────────── */

  _tokenParts(s) {
    const h = hashSeed(String(s));
    return {
      lo: Number(h & 0xFFFFFFFFn) >>> 0,
      hi: Number((h >> 32n) & 0xFFFFFFFFn) >>> 0,
    };
  }

  /* ── Encode ────────────────────────────────────────── */

  encode(msg, tokenStr) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const bytes = strToBytes(msg);
    const { lo, hi } = this._tokenParts(tokenStr);
    const mod = this.module;
    const FS  = 64;
    const frames = [];

    const inPtr = mod._malloc(bytes.length);
    mod.HEAPU8.set(bytes, inPtr);
    const count = mod._enc_begin(inPtr, bytes.length, lo, hi, FS);
    mod._free(inPtr);

    if (count <= 0) {
      console.warn('[codec] encode failed:', mod.UTF8ToString(mod._last_error()));
      return frames;
    }

    const lenPtr = mod._malloc(4);
    for (let i = 0; i < count; i++) {
      mod.setValue(lenPtr, 0, 'i32');
      const ptr = mod._enc_next(lenPtr);
      const len = mod.getValue(lenPtr, 'i32');
      if (!ptr || len <= 0) break;
      frames.push(new Uint8Array(mod.HEAPU8.subarray(ptr, ptr + len)));
    }
    mod._free(lenPtr);
    mod._enc_reset();

    return frames;
  }

  /* ── Feed a coded frame ────────────────────────────── */

  feed(msgId, frameData, tokenStr) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const { lo, hi } = this._tokenParts(tokenStr);
    const key = String(msgId);
    if (!this._partials.has(key)) {
      this._partials.set(key, { frames: [], lo, hi, capacity: 32 });
    }
    this._partials.get(key).frames.push(new Uint8Array(frameData));
    return this._partials.get(key).frames.length;
  }

  /* ── Check if ready to decode ──────────────────────── */

  ready(msgId) {
    const e = this._partials.get(String(msgId));
    return e ? e.frames.length >= 3 : false;
  }

  /* ── Get decoded message ───────────────────────────── */

  get(msgId) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const e = this._partials.get(String(msgId));
    if (!e || !this.ready(msgId)) return null;

    this._partials.delete(String(msgId));
    const mod = this.module;

    /* Feed all frames to the decoder */
    mod._dec_create(e.capacity, e.lo, e.hi);

    let done = false;
    for (const frame of e.frames) {
      const ptr = mod._malloc(frame.length);
      mod.HEAPU8.set(frame, ptr);
      const status = mod._dec_feed(ptr, frame.length);
      mod._free(ptr);

      if (status > 0) {
        done = true;
        break;
      }
    }

    if (!done) {
      mod._dec_reset();
      return null;
    }

    /* Get decoded data */
    const lenPtr = mod._malloc(4);
    mod.setValue(lenPtr, 0, 'i32');
    const outPtr = mod._dec_get(lenPtr);
    const outLen = mod.getValue(lenPtr, 'i32');

    let result = null;
    if (outPtr && outLen > 0) {
      result = bytesToStr(
        new Uint8Array(mod.HEAPU8.subarray(outPtr, outPtr + outLen))
      );
      mod._mem_free(outPtr);
    }
    mod._free(lenPtr);
    mod._dec_reset();

    return result;
  }

  purge(msgId) { this._partials.delete(String(msgId)); }
}

window.CodecBridge = CodecBridge;
