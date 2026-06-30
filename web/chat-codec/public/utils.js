/* ─── utils.js — helpers ────────────────────────────────── */

/** Generate a random hex token (64 bits, 16 hex chars). */
function randomToken() {
  const bytes = new Uint32Array(2);
  crypto.getRandomValues(bytes);
  return bytes[0].toString(16).padStart(8, '0') +
         bytes[1].toString(16).padStart(8, '0');
}

/** Hash a string into a 64‑bit seed (FNV‑1a). */
function hashSeed(str) {
  let h1 = 0x811c9dc5, h2 = 0x6c62272e;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 ^= c; h1 = Math.imul(h1, 0x01000193);
    h2 ^= c; h2 = Math.imul(h2, 0x01dfcd6d);
  }
  return (BigInt(h1) << 32n) | BigInt(h2 >>> 0);
}

/** Convert a string to a Uint8Array. */
function strToBytes(s) {
  return new TextEncoder().encode(s);
}

/** Convert a Uint8Array to a string. */
function bytesToStr(b) {
  return new TextDecoder().decode(b);
}

/** Format a timestamp. */
function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString('pt-PT', { hour:'2-digit', minute:'2-digit' });
}

/** Show a toast notification (auto‑dismiss). */
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

/** Append a system message to the chat box. */
function addSystemMsg(text) {
  const el = document.createElement('div');
  el.className = 'msg system';
  el.textContent = text;
  document.getElementById('messages').appendChild(el);
  el.scrollIntoView({ behavior: 'smooth' });
}

/** Generate a random peer ID for the room. */
function makePeerId(token, nick) {
  const h = hashSeed(token + ':peer:' + nick);
  return 'cs-' + h.toString(36).substring(0, 12);
}

/* Expose to global scope for other modules */
window._utils = { randomToken, hashSeed, strToBytes, bytesToStr, fmtTime, toast, addSystemMsg, makePeerId };
