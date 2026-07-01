/* ─── utils.js — browser helpers ───────────────────────────
 *
 * Depends on: shared/hash.js (loaded first) which provides:
 *   hashSeed, hubId, strToBytes, bytesToStr, fmtTime
 *
 * This file adds browser-specific helpers.
 */

/** Generate a random hex token (64 bits, 16 hex chars). */
function randomToken() {
  const bytes = new Uint32Array(2);
  crypto.getRandomValues(bytes);
  return bytes[0].toString(16).padStart(8, '0') +
         bytes[1].toString(16).padStart(8, '0');
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

/* Expose to global scope */
window._utils = { randomToken, toast, addSystemMsg, makePeerId };
