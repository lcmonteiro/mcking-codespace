#!/usr/bin/env node
/**
 * cli-chat.js — CLI version of CodecShare Chat
 *
 * P2P encrypted chat in the terminal with fountain codes + WebRTC mesh.
 *
 * Usage:
 *   node cli-chat.js --token myroom        # join room (random nick)
 *   node cli-chat.js --token myroom --nick M  # with nickname
 *   node cli-chat.js --token myroom --nick M --codec wasm  # use WASM
 *   node cli-chat.js --help
 *
 * Keys:
 *   Type message and press Enter to send
 *   Ctrl+C or Esc to leave/quit
 *   PageUp/PageDown to scroll messages
 *
 * Dependencies (npm install):
 *   neo-blessed (TUI), peerjs (WebRTC), wrtc (Node.js WebRTC)
 */

/* ─── Parse args ──────────────────────────────────────── */
const args = require('minimist')(process.argv.slice(2), {
  string: ['token', 'nick', 'codec'],
  boolean: ['help'],
  alias: { t: 'token', n: 'nick', c: 'codec', h: 'help' },
  default: { nick: '', codec: 'js' },
});

if (args.help || !args.token) {
  console.log(`
CodecShare Chat — P2P encrypted chat (CLI)

Usage:
  node cli-chat.js --token <room> [--nick <name>] [--codec js|wasm]

Options:
  -t, --token  Room token (required)
  -n, --nick   Nickname (default: auto)
  -c, --codec  Codec: js (default) or wasm
  -h, --help   Show this help

Keys:
  Enter        Send message
  Esc / Ctrl+C Leave room / quit
  PgUp / PgDn  Scroll messages
`);
  process.exit(0);
}

/* ─── Polyfill WebRTC for Node.js ─────────────────────── */
try {
  const wrtc = require('wrtc');
  global.RTCPeerConnection    = wrtc.RTCPeerConnection;
  global.RTCSessionDescription = wrtc.RTCSessionDescription;
  global.RTCIceCandidate      = wrtc.RTCIceCandidate;
  global.MediaStream          = wrtc.MediaStream;
} catch (e) {
  console.error('✖ wrtc not found. Run: npm install');
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
const CHUNK_SIZE    = 65536;
const TOKEN         = args.token;
const NICK          = args.nick || `cli-${crypto.randomBytes(3).toString('hex')}`;
const HUB_PREFIX    = 'cschat';

/* ═══════════════════════════════════════════════════════════
   HELPERS (portable from utils.js)
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
   SIMPLE CODEC (JS fallback, portable from codec.js)
   ═══════════════════════════════════════════════════════════ */

class Codec {
  constructor() {
    this._partials = new Map();
  }

  _tokenParts(s) {
    const h = hashSeed(String(s));
    return {
      lo: Number(h & 0xFFFFFFFFn) >>> 0,
      hi: Number((h >> 32n) & 0xFFFFFFFFn) >>> 0,
    };
  }

  encode(msg, tokenStr) {
    const bytes = strToBytes(msg);
    const seed  = hashSeed(tokenStr);
    const frames = [];

    for (let i = 0; i < 10; i++) {
      const f = Buffer.alloc(8 + bytes.length);
      f.writeBigUInt64LE(seed, 0);
      bytes.copy(f, 8);
      frames.push(f);
    }
    return frames;
  }

  feed(msgId, frameData, tokenStr) {
    const key = String(msgId);
    if (!this._partials.has(key)) {
      this._partials.set(key, { frames: [], tokenStr });
    }
    this._partials.get(key).frames.push(Buffer.from(frameData));
    return this._partials.get(key).frames.length;
  }

  ready(msgId) {
    const e = this._partials.get(String(msgId));
    return e ? e.frames.length >= 5 : false;
  }

  get(msgId) {
    const e = this._partials.get(String(msgId));
    if (!e || !this.ready(msgId)) return null;
    this._partials.delete(String(msgId));
    const frame = e.frames[0];
    return frame.length > 8 ? bytesToStr(frame.slice(8)) : '';
  }

  purge(msgId) {
    this._partials.delete(String(msgId));
  }
}

const codec = new Codec();

/* ═══════════════════════════════════════════════════════════
   TUI SETUP (neo-blessed)
   ═══════════════════════════════════════════════════════════ */

const screen = blessed.screen({
  smartCSR: true,
  title: `🧬 CodecShare Chat — ${TOKEN}`,
  dockBorders: true,
  fullUnicode: true,
});

/* ── Status bar ────────────────────────────────────────── */
const statusBar = blessed.box({
  top: 0,
  left: 0,
  right: 0,
  height: 1,
  style: { fg: 'grey', bg: 'black' },
  tags: true,
});

/* ── Message list ──────────────────────────────────────── */
const msgBox = blessed.box({
  top: 1,
  left: 0,
  right: 0,
  bottom: 3,
  scrollable: true,
  alwaysScroll: true,
  scrollbar: { style: { fg: 'grey' } },
  style: { fg: 'white', bg: 'black' },
  padding: { left: 1, right: 1 },
  tags: true,
});

/* ── Input area ────────────────────────────────────────── */
const inputBox = blessed.textarea({
  bottom: 0,
  left: 0,
  right: 0,
  height: 3,
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

/* ─── TUI helpers ───────────────────────────────────────── */

function updateStatus(text) {
  statusBar.setContent(` {bold}🧬${TOKEN}{/bold} │ ${text} │ {grey}${NICK}{/grey} `);
  screen.render();
}

function addMessage(text, sender, outgoing) {
  const tag = outgoing ? '{green-fg}' : '{cyan-fg}';
  const time = fmtTime(Date.now());
  const prefix = outgoing
    ? ` {bold}${tag}▶{/} {/bold}`
    : ` {bold}${tag}◀{/} {bold}{cyan-fg}${sender}{/}{/bold} `;
  const line = `${prefix}{grey}(${time}){/} ${text}`;
  msgBox.pushLine(line);
  msgBox.setScrollPerc(100);
  screen.render();
}

function addSystemMsg(text) {
  const line = ` {yellow-fg}●{/} {grey}${text}{/}`;
  msgBox.pushLine(line);
  msgBox.setScrollPerc(100);
  screen.render();
}

function addError(text) {
  const line = ` {red-fg}✖{/} {bold}{red-fg}${text}{/}`;
  msgBox.pushLine(line);
  msgBox.setScrollPerc(100);
  screen.render();
}

addSystemMsg('Starting CodecShare Chat…');
updateStatus('Connecting…');

/* ═══════════════════════════════════════════════════════════
   WEBRTC MESH (portable from webrtc.js)
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
        addSystemMsg(`✅ Room created (hub) — ID: ${id}`);
        updateStatus(`Hub — ${id.slice(0,12)}…`);
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
        if (!this.myId) { peer.destroy(); reject(new Error('Timeout connecting to signal server')); }
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
      addSystemMsg(`🟢 Joined room — ID: ${id}`);
      updateStatus(`Peer — ${id.slice(0,12)}…`);
      const conn = peer.connect(hid, {
        reliable: true, serialization: 'binary',
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
      addSystemMsg(`🔗 ${label} connected`);
      updateStatus(`${this.conns.size} peer${this.conns.size !== 1 ? 's' : ''}`);
      this._createParallelChannels(conn, peerId, wrapper);
      if (this.isHub) this._sendPeerList(peerId);
    });

    conn.on('data', (data) => {
      if (typeof data === 'string') {
        this._handleProtocolMsg(data, peerId);
        return;
      }
      this._forwardFrame(data);
    });

    conn.on('close', () => {
      addSystemMsg(`🔌 ${label} disconnected`);
      this.conns.delete(peerId);
      updateStatus(`${this.conns.size} peer${this.conns.size !== 1 ? 's' : ''}`);
    });

    conn.on('error', (err) => addError(`Connection error: ${err.message}`));
  }

  _handleProtocolMsg(jsonStr) {
    try {
      const msg = JSON.parse(jsonStr);
      if (msg.type === 'peer-list' && Array.isArray(msg.peers)) {
        addSystemMsg(`📋 Mesh: ${msg.peers.length} peer${msg.peers.length !== 1 ? 's' : ''}`);
        this.connectToPeers(msg.peers);
      }
    } catch (_) {}
  }

  _forwardFrame(data) {
    if (!this.onFrame) return;
    try {
      const buf = Buffer.from(data);
      if (buf.length < 8) return;
      const msgId = buf.readBigUInt64LE(0);
      this.onFrame(msgId, buf.slice(8));
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

  broadcast(msgId, frameData) {
    if (this.conns.size === 0) return;
    const buf = Buffer.alloc(8 + frameData.length);
    buf.writeBigUInt64LE(msgId, 0);
    if (Buffer.isBuffer(frameData)) frameData.copy(buf, 8);
    else Buffer.from(frameData).copy(buf, 8);

    for (const [pid, w] of this.conns) {
      const chs = w.channels.filter(dc => dc.readyState === 'open');
      if (chs.length > 0) {
        try { chs[Number(msgId % BigInt(chs.length))].send(buf); } catch (_) {}
      } else if (w.conn?.open) {
        try { w.conn.send(buf); } catch (_) {}
      }
    }
  }

  connectToPeers(peers) {
    for (const p of peers) {
      if (p.id === this.myId || this.conns.has(p.id)) continue;
      const conn = this.peer.connect(p.id, {
        reliable: true, serialization: 'binary',
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

const mesh = new ChatMesh();

/* ── Incoming frame ───────────────────────────────────── */
mesh.onFrame = (msgId, frameData) => {
  const count = codec.feed(msgId, frameData, TOKEN);
  if (codec.ready(msgId)) {
    const text = codec.get(msgId);
    if (text && text.length > 0) {
      addMessage(text, 'Peer', false);
      addSystemMsg(`📥 Decoded (${count} frames)`);
    }
    codec.purge(msgId);
  }
};

/* ── Join room ────────────────────────────────────────── */
(async () => {
  try {
    await mesh.createPeer(NICK, TOKEN);
    addSystemMsg('💬 Type your message and press Enter');
    updateStatus(`${mesh.conns.size} peer${mesh.conns.size !== 1 ? 's' : ''}`);
  } catch (e) {
    addError(`Failed: ${e.message}`);
    updateStatus('Error');
  }
})();

/* ── Send message ─────────────────────────────────────── */
inputBox.key('enter', () => {
  const text = inputBox.getValue().trim();
  if (!text) return;
  inputBox.clearValue();
  screen.render();

  const msgId  = mesh.nextMsgId();
  const frames = codec.encode(text, TOKEN);
  if (!frames.length) { addError('Encode failed'); return; }

  for (const f of frames) mesh.broadcast(msgId, f);
  addMessage(text, NICK, true);
  addSystemMsg(`📤 ${frames.length} frame${frames.length > 1 ? 's' : ''}`);
});

/* ── Keybindings ───────────────────────────────────────── */

// Ctrl+C / q / Esc → leave
screen.key(['C-c', 'q', 'escape'], () => {
  addSystemMsg('👋 Leaving room…');
  mesh.disconnect();
  setTimeout(() => process.exit(0), 500);
});

// Focus input on any key
screen.key(['i', 'enter'], () => {
  inputBox.focus();
});

// Scroll messages
msgBox.key(['pageup'], () => { msgBox.scroll(-10); screen.render(); });
msgBox.key(['pagedown'], () => { msgBox.scroll(10); screen.render(); });

// Quit on sigint
process.on('SIGINT', () => {
  mesh.disconnect();
  process.exit(0);
});

screen.render();
