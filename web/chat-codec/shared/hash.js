/* ─── shared/hash.js — hash + utility functions ────────────
 *
 * Dual-mode: CommonJS (Node require) OR browser <script>.
 *
 * Usage (Node):
 *   const { hashSeed, hubId } = require('../shared/hash.js');
 *
 * Usage (Browser, via <script>):
 *   <script src="shared/hash.js"></script>
 *   hashSeed('...')  // available globally
 */
(function (root) {
  'use strict';

  function hashSeed(str) {
    let h1 = 0x811c9dc5, h2 = 0x6c62272e;
    for (let i = 0; i < str.length; i++) {
      const c = str.charCodeAt(i);
      h1 ^= c; h1 = Math.imul(h1, 0x01000193);
      h2 ^= c; h2 = Math.imul(h2, 0x01dfcd6d);
    }
    return (BigInt(h1) << 32n) | BigInt(h2 >>> 0);
  }

  function hubId(token, prefix) {
    prefix = prefix || 'cschat';
    const h = hashSeed(token);
    return prefix + h.toString(36).substring(0, 12);
  }

  function strToBytes(s) {
    if (typeof Buffer !== 'undefined' && Buffer.from) {
      return Buffer.from(s, 'utf-8');
    }
    return new TextEncoder().encode(s);
  }

  function bytesToStr(b) {
    if (typeof Buffer !== 'undefined' && Buffer.from) {
      return b.toString('utf-8');
    }
    return new TextDecoder().decode(b);
  }

  function fmtTime(ts) {
    return new Date(ts).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' });
  }

  const exports = { hashSeed, hubId, strToBytes, bytesToStr, fmtTime };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exports;
  } else {
    /* Browser: set globally */
    for (const key in exports) {
      root[key] = exports[key];
    }
  }
})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
