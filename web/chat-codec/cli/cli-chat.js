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
/* ── From shared modules ── */
const { hubId, fmtTime } = require('../shared/hash.js');
const { CodecBridge } = require('../shared/codec-bridge.cjs');

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
      /* Format: [msgId 8B][dataLen 4B LE][capacity 4B LE][payload...] */
      if (buf.length < 16) return;
      const msgId = buf.readBigUInt64LE(0);
      const dataLen = buf.readUInt32LE(8);
      const capacity = buf.readUInt32LE(12);
      this.onFrame(msgId, buf.slice(16), capacity, dataLen);
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

  broadcast(msgId, frames, capacity, dataLen) {
    if (this.conns.size === 0) return;
    if (!Number.isInteger(capacity) || capacity < 1) capacity = 32;
    if (!Number.isInteger(dataLen) || dataLen < 0) dataLen = 0;

    for (const frameData of frames) {
      const buf = Buffer.alloc(16 + frameData.length);
      buf.writeBigUInt64LE(msgId, 0);
      buf.writeUInt32LE(dataLen, 8);
      buf.writeUInt32LE(capacity, 12);
      if (Buffer.isBuffer(frameData)) frameData.copy(buf, 16);
      else Buffer.from(frameData).copy(buf, 16);

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

mesh.onFrame = (msgId, frameData, capacity, dataLen) => {
  codec.feed(msgId, frameData, TOKEN, capacity, dataLen);
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

  mesh.broadcast(msgId, enc.frames, enc.capacity, enc.dataLen);
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
