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

class CodecBridge {
  constructor() {
    this.module    = null;
    this.ready     = false;
    this._partials = new Map(); /* key -> { frames: [], lo, hi, capacity } */
    this._decoded  = new Set(); /* msgIds already decoded & displayed */
    this._msgCount = 0;
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
      onAbort: (msg) => {
        throw new Error('WASM abort: ' + msg);
      },
    });
    this.module = mod;
    this.ready  = true;
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
    const msgId = ++this._msgCount;
    dbg('[ENCODE] msg=', msg.substring(0, 50), 'bytes=', bytes.length, 'lo=', lo, 'hi=', hi);

    const inPtr = mod._malloc(bytes.length);
    mod.HEAPU8.set(bytes, inPtr);
    const count = mod._enc_begin(inPtr, bytes.length, lo, hi, FS);
    mod._free(inPtr);

    dbg('[ENCODE] enc_begin count=', count);

    if (count <= 0) {
      console.warn('[codec] encode failed:', mod.UTF8ToString(mod._last_error()));
      return { frames, capacity: 0, dataLen: 0 };
    }

    const lenPtr = mod._malloc(4);
    for (let i = 0; i < count; i++) {
      mod.setValue(lenPtr, 0, 'i32');
      const ptr = mod._enc_next(lenPtr);
      const len = mod.getValue(lenPtr, 'i32');
      if (!ptr || len <= 0) break;
      frames.push(new Uint8Array(mod.HEAPU8.subarray(ptr, ptr + len)));
      dbg('[ENCODE] frame', i, 'len=', len);
    }
    mod._free(lenPtr);
    mod._enc_reset();

    const capacity = Math.floor((count - 3) / 2);
    const dataLen = bytes.length;
    dbg('[ENCODE] done: frames=', frames.length, 'capacity=', capacity,
        'dataLen=', dataLen);
    return { frames, capacity, dataLen };
  }

  /* ── Feed a coded frame ────────────────────────────── */

  feed(msgId, frameData, tokenStr, capacity, dataLen) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const key = String(msgId);

    /* Skip if already decoded this message */
    if (this._decoded.has(key)) {
      dbg('[FEED] SKIP — msgId already decoded:', msgId);
      return;
    }

    const { lo, hi } = this._tokenParts(tokenStr);
    if (!this._partials.has(key)) {
      /* Store capacity and dataLen from first frame */
      const cap = (capacity && capacity > 0) ? capacity : 32;
      const dlen = (Number.isInteger(dataLen) && dataLen >= 0) ? dataLen : 0;
      dbg('[FEED] new msgId=', msgId, 'capacity=', cap, 'dataLen=', dlen,
          'lo=', lo, 'hi=', hi);
      this._partials.set(key, {
        frames: [], lo, hi,
        capacity: cap,
        dataLen: dlen
      });
    }
    const entry = this._partials.get(key);
    entry.frames.push(new Uint8Array(frameData));
    dbg('[FEED] msgId=', msgId, 'frameLen=', frameData.length,
        'totalFrames=', entry.frames.length, 'capacity=', entry.capacity,
        'dataLen=', entry.dataLen);
  }

  /* ── Try to decode an accumulated message ──────────── */
  /*
   * After each new frame, try to decode everything accumulated so far.
   * If decode succeeds, returns { text, frameCount } and cleans up.
   * If not enough frames yet, returns null (keeps accumulating).
   */
  tryDecode(msgId) {
    if (!this.ready || !this.module) {
      throw new Error('CodecBridge not initialized');
    }
    const key = String(msgId);
    const e = this._partials.get(key);
    if (!e || e.frames.length === 0) {
      dbg('[DECODE] msgId=', msgId, 'no partial data');
      return null;
    }

    const mod = this.module;
    dbg('[DECODE] msgId=', msgId, 'frames=', e.frames.length,
        'capacity=', e.capacity, 'firstFrameLen=', e.frames[0].length);

    /* Create decoder and feed ALL accumulated frames */
    const created = mod._dec_create(e.capacity, e.lo, e.hi);
    dbg('[DECODE] dec_create=', created, 'capacity=', e.capacity);
    if (!created) {
      console.warn('[codec] dec_create failed:', mod.UTF8ToString(mod._last_error()));
      return null;
    }

    let done = false;
    let feedCount = 0;
    for (const frame of e.frames) {
      feedCount++;
      const ptr = mod._malloc(frame.length);
      mod.HEAPU8.set(frame, ptr);
      const status = mod._dec_feed(ptr, frame.length);
      mod._free(ptr);
      dbg('[DECODE] feed', feedCount, '/', e.frames.length, 'status=',
          status, 'len=', frame.length);

      if (status > 0) {
        done = true;
        dbg('[DECODE] decode succeeded after', feedCount, 'frames');
        break;
      } else if (status === -1) {
        const err = mod.UTF8ToString(mod._last_error());
        console.warn('[codec] dec_feed error:', err);
        dbg('[DECODE] feed ERROR:', err);
        /* Continue anyway — maybe next frame fixes it */
      }
    }

    if (!done) {
      dbg('[DECODE] not enough frames yet (', e.frames.length, '/',
          e.capacity, ')');
      mod._dec_reset();
      return null;
    }

    /* Get decoded data — use dataLen from transport protocol */
    const lenPtr = mod._malloc(4);
    mod.setValue(lenPtr, 0, 'i32');

    let outPtr, outLen;
    if (e.dataLen > 0) {
      /* Use dec_get_ex with transport-provided data length */
      outPtr = mod._dec_get_ex(lenPtr, e.dataLen);
      outLen = mod.getValue(lenPtr, 'i32');
      dbg('[DECODE] dec_get_ex: outPtr=', !!outPtr, 'outLen=', outLen,
          'dataLen=', e.dataLen);
    } else {
      /* Fallback to original dec_get (uses g_orig_data_len from last enc_begin) */
      outPtr = mod._dec_get(lenPtr);
      outLen = mod.getValue(lenPtr, 'i32');
      dbg('[DECODE] dec_get (fallback): outPtr=', !!outPtr, 'outLen=', outLen);
    }

    let result = null;
    if (outPtr && outLen > 0) {
      const rawBytes = new Uint8Array(mod.HEAPU8.subarray(outPtr, outPtr + outLen));
      dbg('[DECODE] raw first bytes (hex):', Array.from(rawBytes.slice(0, 8))
          .map(b => b.toString(16).padStart(2, '0')).join(' '));
      const text = bytesToStr(rawBytes);
      mod._mem_free(outPtr);
      result = { text, frameCount: e.frames.length };
      dbg('[DECODE] SUCCESS textLen=', text.length, 'frameCount=', e.frames.length);
    } else if (outPtr && outLen === 0) {
      /* Empty message (e.g. 0 bytes) is valid */
      result = { text: '', frameCount: e.frames.length };
      mod._mem_free(outPtr);
      dbg('[DECODE] SUCCESS empty message');
    } else {
      const err = mod.UTF8ToString(mod._last_error());
      dbg('[DECODE] dec_get failed:', err);
    }
    mod._free(lenPtr);
    mod._dec_reset();

    /* Mark as decoded so future frames for this msgId are skipped */
    if (result) {
      this._partials.delete(key);
      this._decoded.add(key);
      dbg('[DECODE] added to _decoded set, size=', this._decoded.size);

      /* Prune old entries (keep last 100) */
      if (this._decoded.size > 200) {
        const entries = [...this._decoded];
        this._decoded = new Set(entries.slice(-100));
        dbg('[DECODE] pruned _decoded set to 100 entries');
      }
    }

    return result;
  }

  purge(msgId) { this._partials.delete(String(msgId)); }

  /* ── Reset state (e.g. when leaving a room) ────────── */

  reset() {
    this._partials.clear();
    this._decoded.clear();
    dbg('[CODEC] state reset');
  }
}

window.CodecBridge = CodecBridge;
