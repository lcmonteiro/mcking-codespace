/* ─── codec.js — WASM codec-share bridge + JS fallback ─────
 *
 * Wraps the Emscripten CodecShare module (istream/ostream API).
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
 * Token → seed: FNV‑1a 64‑bit → lo (u32) / hi (u32)
 *   (WASM FFI uses two u32 for uint64_t compat)
 */

class CodecBridge {
  constructor() {
    this.module    = null;
    this.ready     = false;
    this._fallback = false;
    this._partials = new Map(); /* key → { frames: [], lo, hi } */
  }

  /* ── Init WASM (or fallback) ───────────────────────── */

  async init() {
    if (this.ready) return;
    if (typeof CodecShare === 'undefined') {
      console.warn('[codec] WASM not loaded → JS fallback');
      this._fallback = true;
      this.ready     = true;
      return;
    }
    return new Promise((resolve) => {
      CodecShare({
        onRuntimeInitialized: () => {
          this.module = CodecShare;
          this.ready  = true;
          console.log('[codec] WASM ready');
          resolve();
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
    const bytes = strToBytes(msg);
    const { lo, hi } = this._tokenParts(tokenStr);
    const frames = [];

    if (this._fallback) {
      for (let i = 0; i < 10; i++) {
        const f = new Uint8Array(8 + bytes.length);
        new DataView(f.buffer, 0, 8).setBigUint64(0, hashSeed(tokenStr), true);
        f.set(bytes, 8);
        frames.push(f);
      }
      return frames;
    }

    const mod    = this.module;
    const FS     = 64;               /* frame chunk size */
    const inPtr  = mod._malloc(bytes.length);
    mod.HEAPU8.set(bytes, inPtr);
    const count  = mod._enc_begin(inPtr, bytes.length, lo, hi, FS);
    mod._free(inPtr);

    if (count <= 0) {
      console.warn('[codec] encode failed');
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
    const { lo, hi } = this._tokenParts(tokenStr);
    const key = String(msgId);
    if (!this._partials.has(key)) {
      this._partials.set(key, { frames: [], lo, hi });
    }
    this._partials.get(key).frames.push(new Uint8Array(frameData));
    return this._partials.get(key).frames.length;
  }

  /* ── Check if ready to decode ──────────────────────── */

  ready(msgId) {
    const e = this._partials.get(String(msgId));
    return e ? e.frames.length >= 5 : false;  /* need a few frames */
  }

  /* ── Get decoded message ───────────────────────────── */

  get(msgId) {
    const e = this._partials.get(String(msgId));
    if (!e || !this.ready(msgId)) return null;

    this._partials.delete(String(msgId));

    if (this._fallback) return bytesToStr(e.frames[0].slice(8));

    const mod = this.module;

    /* Each frame is self‑contained. Try each until one works. */
    for (const frame of e.frames) {
      mod._dec_create(e.lo, e.hi);

      const ptr = mod._malloc(frame.length);
      mod.HEAPU8.set(frame, ptr);
      const status = mod._dec_feed(ptr, frame.length);
      mod._free(ptr);

      if (status > 0 && mod._dec_ready() > 0) {
        const lenPtr = mod._malloc(4);
        mod.setValue(lenPtr, 0, 'i32');
        const outPtr = mod._dec_get(lenPtr);
        const outLen = mod.getValue(lenPtr, 'i32');

        let result = null;
        if (outPtr && outLen > 0) {
          result = bytesToStr(new Uint8Array(mod.HEAPU8.subarray(outPtr, outPtr + outLen)));
          mod._mem_free(outPtr);
        }
        mod._free(lenPtr);
        mod._dec_reset();
        return result;
      }

      mod._dec_reset();
    }

    return null;
  }

  purge(msgId) { this._partials.delete(String(msgId)); }
}

window.CodecBridge = CodecBridge;
