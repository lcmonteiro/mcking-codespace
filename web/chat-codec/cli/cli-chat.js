#!/usr/bin/env node
/**
 * cli-chat.js — CLI version of CodecShare Chat
 *
 * P2P encrypted chat in the terminal with fountain codes + WebRTC mesh.
 * Requires codec_share.wasm (compiled via wasm/build.sh).
 *
 * Usage:
 *   node cli-chat.js --token ***              # join room
 *   node cli-chat.js --token *** --nick M     # with nickname
 *   node cli-chat.js --help
 *
 * Keys:
 *   Enter         Send message
 *   Esc / Ctrl+C  Leave room / quit
 *   PgUp / PgDn   Scroll messages
 *
 * Dependencies (npm install):
 *   neo-blessed (TUI), peerjs (WebRTC), wrtc (Node.js WebRTC)
 */

/* ─── Parse args ──────────────────────────────────────── */
const minimist = require('minimist');
const args = minimist(process.argv.slice(2), {
  string: ['token', 'nick'],
  boolean: ['help'],
  alias: { t: 'token', n: 'nick', h: 'help' },
  default: { nick: '' },
});

if (args.help || !args.token) {
  console.log(`
CodecShare Chat — P2P encrypted chat (CLI)

Usage:
  node cli-chat.js --token <room> [--nick <name>]

Options:
  -t, --token  Room token (required)
  -n, --nick   Nickname (default: auto)
  -h, --help   Show this help

Keys:
  Enter        Send message
  Esc / Ctrl+C Leave room / quit
  PgUp / PgDn  Scroll messages

Requires codec_share.wasm compiled via wasm/build.sh.
`);
  process.exit(0);
}

/* ─── Polyfill WebRTC for Node.js ─────────────────────── */
// PeerJS for Node.js needs window + WebRTC globals (uses wrtc)
globalThis.window = globalThis;
try {
  const wrtc = require('@roamhq/wrtc');
  globalThis.RTCPeerConnection    = wrtc.RTCPeerConnection;
  globalThis.RTCSessionDescription = wrtc.RTCSessionDescription;
  globalThis.RTCIceCandidate      = wrtc.RTCIceCandidate;
  globalThis.MediaStream          = wrtc.MediaStream;
} catch (e) {
  console.error('✖ @roamhq/wrtc not found. Run: npm install');
  process.exit(1);
}

const { Peer }   = require('peerjs');
const blessed    = require('neo-blessed');
const crypto     = require('crypto');
const path       = require('path');
const fs         = require('fs');

/* ═══════════════════════════════════════════════════════════
   CONFIG
   ═══════════════════════════════════════════════════════════ */

const CHANNEL_COUNT = 4;
const TOKEN         = args.token;
const NICK          = args.nick || `cli-${crypto.randomBytes(3).toString('hex')}`;
const HUB_PREFIX    = 'cschat';
const WASM_DIR      = path.join(__dirname, '..', 'public');

/* ═══════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════ */

function hashSeed(str) {
  let h1 = 0x811c9dc5, h2 = 0x6c62272e;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 ^= c; h1 = Math.imul(h1, 0x01000193);
    h2 ^= c; h2 = Math.imul(h2, 0x01dfcd6d);
  }
  return (BigInt(h1) << 32n) | BigInt(h2 >>> 0);
}

function hubId(token) {
  const h = hashSeed(token);
  return HUB_PREFIX + h.toString(36).substring(0, 12);
}

function strToBytes(s) { return Buffer.from(s, 'utf-8'); }
function bytesToStr(b) { return b.toString('utf-8'); }

function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString('pt-PT', { hour:'2-digit', minute:'2-digit' });
}

/* ═══════════════════════════════════════════════════════════
   WASM CODEC BRIDGE (port of public/codec.js for Node.js)
   ═══════════════════════════════════════════════════════════ */

class CodecBridge {
  constructor() {
    this.module    = null;
    this.ready     = false;
    this._partials = new Map();
  }

  async init() {
    if (this.ready) return;

    const wasmJsPath = path.join(WASM_DIR, 'codec_share.js');
    if (!fs.existsSync(wasmJsPath)) {
      throw new Error(
        `codec_share.js not found at ${wasmJsPath}\n` +
        `Run: bash wasm/build.sh  (requires Emscripten)`
      );
    }

    /* Load the Emscripten module (it's a function that returns a promise) */
    const CodecShare = require(wasmJsPath);

    /* Tell it where to find the .wasm file (same directory) */
    const wasmBinaryFile = path.join(WASM_DIR, 'codec_share.wasm');
    if (!fs.existsSync(wasmBinaryFile)) {
      throw new Error(
        `codec_share.wasm not found at ${wasmBinaryFile}\n` +
        `Run: bash wasm/build.sh`
      );
    }

    const mod = await CodecShare({
      locateFile: (file) => path.join(WASM_DIR, file),
      onAbort: (msg) => { throw new Error('WASM abort: ' + msg); },
    });
    this.module = mod;
    this.ready  = true;
    console.log('[codec] WASM ready, ping:', mod._ping());
  }

  _tokenParts(s) {
    const h = hashSeed(String(s));
    return {
      lo: Number(h & 0xFFFFFFFFn) >>> 0,
      hi: Number((h >> 32n) & 0xFFFFFFFFn) >>> 0,
    };
  }

  encode(msg, tokenStr) {
    if (!this.ready || !this.module) throw new Error('CodecBridge not initialized');
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
      return { frames, capacity: 0 };
    }

    const lenPtr = mod._malloc(4);
    for (let i = 0; i < count; i++) {
      mod.setValue(lenPtr, 0, 'i32');
      const ptr = mod._enc_next(lenPtr);
      const len = mod.getValue(lenPtr, 'i32');
      if (!ptr || len <= 0) break;
      frames.push(Buffer.from(mod.HEAPU8.subarray(ptr, ptr + len)));
    }
    mod._free(lenPtr);
    mod._enc_reset();

    const capacity = Math.floor((count - 3) / 2);
    return { frames, capacity };
  }

  feed(msgId, frameData, tokenStr, capacity) {
    if (!this.ready || !this.module) throw new Error('CodecBridge not initialized');
    const { lo, hi } = this._tokenParts(tokenStr);
    const key = String(msgId);
    if (!this._partials.has(key)) {
      this._partials.set(key, { frames: [], lo, hi,
        capacity: (capacity && capacity > 0) ? capacity : 32 });
    }
    this._partials.get(key).frames.push(Buffer.from(frameData));
  }

  /*
   * Try to decode all accumulated frames for msgId.
   * Returns { text, frameCount } on success, null if still accumulating.
   * Only purges partials on successful decode.
   */
  tryDecode(msgId) {
    if (!this.ready || !this.module) throw new Error('CodecBridge not initialized');
    const e = this._partials.get(String(msgId));
    if (!e || e.frames.length === 0) return null;

    const mod = this.module;

    mod._dec_create(e.capacity ?? 32, e.lo, e.hi);

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

    const lenPtr = mod._malloc(4);
    mod.setValue(lenPtr, 0, 'i32');
    const outPtr = mod._dec_get(lenPtr);
    const outLen = mod.getValue(lenPtr, 'i32');

    let result = null;
    if (outPtr && outLen > 0) {
      const text = bytesToStr(Buffer.from(mod.HEAPU8.subarray(outPtr, outPtr + outLen)));
      mod._mem_free(outPtr);
      result = { text, frameCount: e.frames.length };
    }
    mod._free(lenPtr);
    mod._dec_reset();

    if (result) {
      this._partials.delete(String(msgId));
    }

    return result;
  }

  purge(msgId) { this._partials.delete(String(msgId)); }
}

/* ═══════════════════════════════════════════════════════════
   TUI SETUP (neo-blessed)
   ═══════════════════════════════════════════════════════════ */

const screen = blessed.screen({
  smartCSR: true,
  title: `CodecShare Chat -- ${TOKEN}`,
  dockBorders: true,
  fullUnicode: true,
});

const statusBar = blessed.box({
  top: 0, left: 0, right: 0, height: 1,
  style: { fg: 'grey', bg: 'black' }, tags: true,
});

const msgBox = blessed.box({
  top: 1, left: 0, right: 0, bottom: 3,
  scrollable: true, alwaysScroll: true,
  scrollbar: { style: { fg: 'grey' } },
  style: { fg: 'white', bg: 'black' },
  padding: { left: 1, right: 1 }, tags: true,
});

const inputBox = blessed.textarea({
  bottom: 0, left: 0, right: 0, height: 3,
  inputOnFocus: true,
  style: { fg: 'white', bg: 'black', focus: { bg: '#111122' } },
  border: { type: 'line', fg: '#6c5ce7' },
  padding: { top: 0, left: 1 },
});

screen.append(statusBar);
screen.append(msgBox);
screen.append(inputBox);
inputBox.focus();
screen.render();

function updateStatus(text) {
  statusBar.setContent(` {bold}${TOKEN}{/bold} | ${text} | {grey}${NICK}{/grey} `);
  screen.render();
}

function addMessage(text, sender, outgoing) {
  const tag = outgoing ? '{green-fg}' : '{cyan-fg}';
  const time = fmtTime(Date.now());
  const prefix = outgoing
    ? ` {bold}${tag}>{/} {/bold}`
    : ` {bold}${tag}<{/} {bold}{cyan-fg}${sender}{/}{/bold} `;
  const line = `${prefix}{grey}(${time}){/} ${text}`;
  msgBox.pushLine(line);
  msgBox.setScrollPerc(100);
  screen.render();
}

function addSystemMsg(text) {
  msgBox.pushLine(` {yellow-fg}*{/} {grey}${text}{/}`);
  msgBox.setScrollPerc(100);
  screen.render();
}

function addError(text) {
  msgBox.pushLine(` {red-fg}X{/} {bold}{red-fg}${text}{/}`);
  msgBox.setScrollPerc(100);
  screen.render();
}

addSystemMsg('Starting CodecShare Chat...');

/* ═══════════════════════════════════════════════════════════
   WEBRTC MESH
   ═══════════════════════════════════════════════════════════ */

class ChatMesh {
  constructor() {
    this.peer    = null;
    this.myId    = null;
    this.nick    = NICK;
    this.token   = TOKEN;
    this.isHub   = false;
    this.conns   = new Map();
    this.onFrame = null;
    this._msgCounter = 0n;
  }

  async createPeer(nick, token) {
    this.nick  = nick;
    this.token = token;
    const hid  = hubId(token);

    return new Promise((resolve, reject) => {
      const peer = new Peer(hid, {
        config: { iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' },
        ]}
      });

      peer.on('open', (id) => {
        this.peer  = peer;
        this.myId  = id;
        this.isHub = true;
        addSystemMsg(`Room created (hub) -- ID: ${id}`);
        updateStatus(`Hub -- ${id.slice(0,12)}...`);
        resolve(id);
      });

      peer.on('connection', (conn) => this._handleConn(conn));

      peer.on('error', (err) => {
        if (err.type === 'unavailable-id') {
          peer.destroy();
          this._joinAsPeer(nick, token, hid, resolve, reject);
        } else {
          addError(`Peer error: ${err.message}`);
          reject(err);
        }
      });

      setTimeout(() => {
        if (!this.myId) { peer.destroy(); reject(new Error('Timeout')); }
      }, 20000);
    });
  }

  _joinAsPeer(nick, token, hid, resolve, reject) {
    const peer = new Peer({
      config: { iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
      ]}
    });

    peer.on('open', (id) => {
      this.peer  = peer;
      this.myId  = id;
      this.isHub = false;
      addSystemMsg(`Joined room -- ID: ${id}`);
      updateStatus(`Peer -- ${id.slice(0,12)}...`);
      const conn = peer.connect(hid, {
        reliable: true,
        metadata: { nick: this.nick, type: 'join-request' }
      });
      this._setupConn(conn, hid, 'Hub');
      resolve(id);
    });

    peer.on('connection', (conn) => this._handleConn(conn));
    peer.on('error', (err) => reject(err));
  }

  _handleConn(conn) {
    const meta = conn.metadata || {};
    const label = meta.nick || conn.peer.slice(0, 8);
    this._setupConn(conn, conn.peer, label);
  }

  _setupConn(conn, peerId, label) {
    if (this.conns.has(peerId)) return;
    const wrapper = { conn, peerId, label, channels: [] };
    this.conns.set(peerId, wrapper);

    conn.on('open', () => {
      addSystemMsg(`${label} connected`);
      updateStatus(`${this.conns.size} peer${this.conns.size !== 1 ? 's' : ''}`);
      this._createParallelChannels(conn, peerId, wrapper);
      if (this.isHub) this._sendPeerList(peerId);
    });

    conn.on('data', (data) => {
      if (typeof data === 'string') { this._handleProtocolMsg(data); return; }
      this._forwardFrame(data);
    });

    conn.on('close', () => {
      addSystemMsg(`${label} disconnected`);
      this.conns.delete(peerId);
      updateStatus(`${this.conns.size} peer${this.conns.size !== 1 ? 's' : ''}`);
    });

    conn.on('error', (err) => addError(`Connection error: ${err.message}`));
  }

  _handleProtocolMsg(jsonStr) {
    try {
      const msg = JSON.parse(jsonStr);
      if (msg.type === 'peer-list' && Array.isArray(msg.peers)) {
        addSystemMsg(`Mesh: ${msg.peers.length} peer${msg.peers.length !== 1 ? 's' : ''}`);
        this.connectToPeers(msg.peers);
      }
    } catch (_) {}
  }

  _forwardFrame(data) {
    if (!this.onFrame) return;
    try {
      const buf = Buffer.from(data);
      /* Format: [msgId 8B][capacity 4B LE][payload...] */
      if (buf.length < 12) return;
      const msgId = buf.readBigUInt64LE(0);
      const capacity = buf.readUInt32LE(8);
      this.onFrame(msgId, buf.slice(12), capacity);
    } catch (_) {}
  }

  _createParallelChannels(conn, peerId, wrapper) {
    const pc = conn._peerConnection;
    if (!pc) return;
    for (let i = 0; i < CHANNEL_COUNT; i++) {
      try {
        const dc = pc.createDataChannel(`cs-${i}`, {
          ordered: false, maxRetransmits: 0
        });
        dc.binaryType = 'nodebuffer';
        dc.onmessage = (ev) => this._forwardFrame(ev.data);
        wrapper.channels.push(dc);
      } catch (_) {}
    }
    pc.ondatachannel = (ev) => {
      const dc = ev.channel;
      if (!dc.label.startsWith('cs-')) return;
      dc.binaryType = 'nodebuffer';
      dc.onmessage = (ev) => this._forwardFrame(ev.data);
      wrapper.channels.push(dc);
    };
  }

  _sendPeerList(remoteId) {
    const peers = Array.from(this.conns.keys())
      .filter(p => p !== remoteId)
      .map(id => ({ id, nick: this.conns.get(id)?.label || id.slice(0, 8) }));
    const wrapper = this.conns.get(remoteId);
    if (wrapper && wrapper.conn?.open) {
      wrapper.conn.send(JSON.stringify({ type: 'peer-list', peers }));
    }
  }

  broadcast(msgId, frames, capacity) {
    if (this.conns.size === 0) return;
    if (!Number.isInteger(capacity) || capacity < 1) capacity = 32;

    for (const frameData of frames) {
      const buf = Buffer.alloc(12 + frameData.length);
      buf.writeBigUInt64LE(msgId, 0);
      buf.writeUInt32LE(capacity, 8);
      if (Buffer.isBuffer(frameData)) frameData.copy(buf, 12);
      else Buffer.from(frameData).copy(buf, 12);

      for (const [pid, w] of this.conns) {
        const chs = w.channels.filter(dc => dc.readyState === 'open');
        if (chs.length > 0) {
          try { chs[Number(msgId % BigInt(chs.length))].send(buf); } catch (_) {}
        } else if (w.conn?.open) {
          try { w.conn.send(buf); } catch (_) {}
        }
      }
    }
  }

  connectToPeers(peers) {
    for (const p of peers) {
      if (p.id === this.myId || this.conns.has(p.id)) continue;
      const conn = this.peer.connect(p.id, {
        reliable: true,
        metadata: { nick: this.nick }
      });
      this._setupConn(conn, p.id, p.nick);
    }
  }

  nextMsgId() {
    this._msgCounter++;
    return (BigInt(this.myId?.length || 0) << 48n) | this._msgCounter;
  }

  disconnect() {
    for (const [_, w] of this.conns) {
      for (const dc of w.channels) try { dc.close(); } catch (_) {}
      try { w.conn.close(); } catch (_) {}
    }
    this.conns.clear();
    if (this.peer) { this.peer.destroy(); this.peer = null; }
    this.myId = null; this.isHub = false;
  }
}

/* ═══════════════════════════════════════════════════════════
   APP LOGIC
   ═══════════════════════════════════════════════════════════ */

const codec = new CodecBridge();
const mesh  = new ChatMesh();

mesh.onFrame = (msgId, frameData, capacity) => {
  codec.feed(msgId, frameData, TOKEN, capacity);
  const result = codec.tryDecode(msgId);
  if (result) {
    addMessage(result.text, 'Peer', false);
    addSystemMsg(`Decoded (${result.frameCount} frames)`);
  }
};

(async () => {
  try {
    updateStatus('Initializing codec...');
    await codec.init();
    addSystemMsg('Codec ready');

    await mesh.createPeer(NICK, TOKEN);
    addSystemMsg('Type your message and press Enter');
    updateStatus(`${mesh.conns.size} peer${mesh.conns.size !== 1 ? 's' : ''}`);
  } catch (e) {
    addError(`Failed: ${e.message}`);
    updateStatus('Error');
  }
})();

inputBox.key('enter', () => {
  const text = inputBox.getValue().trim();
  if (!text) return;
  inputBox.clearValue();
  screen.render();

  const msgId  = mesh.nextMsgId();
  const enc = codec.encode(text, TOKEN);
  if (!enc.frames.length) { addError('Encode failed'); return; }

  mesh.broadcast(msgId, enc.frames, enc.capacity);
  addMessage(text, NICK, true);
  addSystemMsg(`${frames.length} frame${frames.length > 1 ? 's' : ''} sent`);
});

screen.key(['C-c', 'q', 'escape'], () => {
  addSystemMsg('Leaving room...');
  mesh.disconnect();
  setTimeout(() => process.exit(0), 500);
});

screen.key(['i', 'enter'], () => { inputBox.focus(); });
msgBox.key(['pageup'], () => { msgBox.scroll(-10); screen.render(); });
msgBox.key(['pagedown'], () => { msgBox.scroll(10); screen.render(); });

process.on('SIGINT', () => { mesh.disconnect(); process.exit(0); });

screen.render();
