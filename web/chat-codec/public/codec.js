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

const DEBUG = true;
function dbg(...args) {
  if (DEBUG) console.log('[codec]', ...args, 'at', Date.now());
}

/**
 * CodecBridge — WASM codec-share bridge (instance-based)
 *
 * Direct port of BufferShare/Android JNI pattern:
 *   - createEncoder() stores dataLen per-instance
 *   - createDecoder(id, capacity, dataLen, token) upfront
 *   - decSet(id, frame) → 0=need more, 1=done, -1=error
 *   - decGet(id) → uses per-instance dataLen
 */

const DEBUG = true;
function dbg(...args) {
  if (DEBUG) console.log('[codec]', ...args, 'at', Date.now());
}

class CodecBridge {
  constructor() {
    this.module     = null;
    this.ready      = false;
    this._lenPtr    = null;
    /* Map<msgId, { encoderId, decoderId, frames, capacity, dataLen, lo, hi }> */
    this._partials  = new Map();
    this._decoded   = new Set();
    this._msgCount  = 0;
    this._encHandle = null;  /* persistent encoder handle for outbound */
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
    const mod = await CodecShare({
      onAbort: (msg) => { throw new Error('WASM abort: ' + msg); },
    });
    this.module  = mod;
    this._lenPtr = mod._malloc(4);
    this.ready   = true;
    this._encHandle = mod._create_encoder();
    console.log('[codec] WASM ready, ping:', mod._ping());
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
    dbg('[ENCODE] msg=', msg.substring(0, 50), 'bytes=', bytes.length);

    const inPtr = mod._malloc(bytes.length);
    mod.HEAPU8.set(bytes, inPtr);
    const count = mod._enc_set(this._encHandle, inPtr, bytes.length, lo, hi, FS);
    mod._free(inPtr);

    dbg('[ENCODE] enc_set count=', count);

    if (count <= 0) {
      console.warn('[codec] encode failed:', mod.UTF8ToString(mod._last_error()));
      return { frames, capacity: 0, dataLen: 0 };
    }

    const lp = this._lenPtr;
    for (let i = 0; i < count; i++) {
      mod.setValue(lp, 0, 'i32');
      const ptr = mod._enc_get(this._encHandle, lp);
      const flen = mod.getValue(lp, 'i32');
      if (!ptr || flen <= 0) break;
      frames.push(new Uint8Array(mod.HEAPU8.subarray(ptr, ptr + flen)));
      dbg('[ENCODE] frame', i, 'len=', flen);
    }

    const capacity = Math.floor((count - 3) / 2);
    dbg('[ENCODE] done: frames=', frames.length, 'capacity=', capacity,
        'dataLen=', bytes.length);
    return { frames, capacity, dataLen: bytes.length };
  }

  /* ── Feed a coded frame ────────────────────────────── */

  feed(msgId, frameData, tokenStr, capacity, dataLen) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const key = String(msgId);

    if (this._decoded.has(key)) {
      dbg('[FEED] SKIP — msgId already decoded:', msgId);
      return;
    }

    const { lo, hi } = this._tokenParts(tokenStr);

    if (!this._partials.has(key)) {
      /* Create a decoder instance for this msgId */
      const cap  = (capacity && capacity > 0) ? capacity : 32;
      const dlen = (Number.isInteger(dataLen) && dataLen >= 0) ? dataLen : 0;
      const decoderId = this.module._create_decoder();
      this.module._dec_create(decoderId, cap, dlen, lo, hi);
      dbg('[FEED] new msgId=', msgId, 'decoderId=', decoderId,
          'capacity=', cap, 'dataLen=', dlen);
      this._partials.set(key, {
        frames: [], decoderId, capacity: cap, dataLen: dlen
      });
    }

    const entry = this._partials.get(key);
    entry.frames.push(new Uint8Array(frameData));
    dbg('[FEED] msgId=', msgId, 'frameLen=', frameData.length,
        'totalFrames=', entry.frames.length, 'capacity=', entry.capacity);
  }

  /* ── Try to decode ─────────────────────────────────── */

  tryDecode(msgId) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const key = String(msgId);
    const e = this._partials.get(key);
    if (!e || e.frames.length === 0) return null;

    const mod = this.module;
    const did = e.decoderId;
    const lp  = this._lenPtr;

    dbg('[DECODE] msgId=', msgId, 'frames=', e.frames.length,
        'capacity=', e.capacity, 'decoderId=', did);

    let done = false;
    for (let i = 0; i < e.frames.length; i++) {
      const frame = e.frames[i];
      const fp = mod._malloc(frame.length);
      mod.HEAPU8.set(frame, fp);
      const st = mod._dec_set(did, fp, frame.length);
      mod._free(fp);
      dbg('[DECODE] dec_set', i, ':', st);

      if (st > 0) {
        done = true;
        break;
      } else if (st === -1) {
        console.warn('[codec] dec_set error:', mod.UTF8ToString(mod._last_error()));
      }
    }

    if (!done) return null;

    /* Get decoded data (uses per-instance dataLen) */
    mod.setValue(lp, 0, 'i32');
    const outPtr = mod._dec_get(did, lp);
    const outLen = mod.getValue(lp, 'i32');
    dbg('[DECODE] dec_get: outPtr=', !!outPtr, 'outLen=', outLen);

    let result = null;
    if (outPtr && outLen > 0) {
      const rawBytes = new Uint8Array(mod.HEAPU8.subarray(outPtr, outPtr + outLen));
      const text = bytesToStr(rawBytes);
      mod._mem_free(outPtr);
      result = { text, frameCount: e.frames.length };
      dbg('[DECODE] SUCCESS textLen=', text.length);
    } else if (outPtr && outLen === 0) {
      result = { text: '', frameCount: e.frames.length };
      mod._mem_free(outPtr);
    }

    /* Cleanup */
    mod._destroy_decoder(did);
    this._partials.delete(key);

    if (result) {
      this._decoded.add(key);
      if (this._decoded.size > 200) {
        const entries = [...this._decoded];
        this._decoded = new Set(entries.slice(-100));
      }
    }

    return result;
  }

  purge(msgId) {
    const key = String(msgId);
    const e = this._partials.get(key);
    if (e) {
      this.module._destroy_decoder(e.decoderId);
      this._partials.delete(key);
    }
  }

  reset() {
    for (const [k, e] of this._partials) {
      this.module._destroy_decoder(e.decoderId);
    }
    this._partials.clear();
    this._decoded.clear();
    dbg('[CODEC] state reset');
  }
}

window.CodecBridge = CodecBridge;
