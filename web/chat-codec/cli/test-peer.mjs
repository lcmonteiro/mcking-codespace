/**
 * test-peer.mjs — Minimal PeerJS test (hub + peer)
 * Run TWO instances: node test-peer.mjs --hub
 *                   node test-peer.mjs --peer <hub-id>
 */
import path from 'path';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const _require = createRequire(import.meta.url);

globalThis.window = globalThis;

// WebRTC polyfill
const wrtc = _require('@roamhq/wrtc');
globalThis.RTCPeerConnection    = wrtc.RTCPeerConnection;
globalThis.RTCSessionDescription = wrtc.RTCSessionDescription;
globalThis.RTCIceCandidate      = wrtc.RTCIceCandidate;
globalThis.MediaStream          = wrtc.MediaStream;

const { Peer, PeerErrorType } = _require('peerjs');
const minimist = _require('minimist');
const args = minimist(process.argv.slice(2));

function hashSeed(str) {
  let h1 = 0x811c9dc5, h2 = 0x6c62272e;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 ^= c; h1 = Math.imul(h1, 0x01000193);
    h2 ^= c; h2 = Math.imul(h2, 0x01dfcd6d);
  }
  return (BigInt(h1) << 32n) | BigInt(h2 >>> 0);
}

const HUB_PREFIX = 'cschat';
function hubId(token) {
  const h = hashSeed(token);
  return HUB_PREFIX + h.toString(36).substring(0, 12);
}

const TOKEN = args.token || 'test123';
const hid = hubId(TOKEN);
console.log('token:', TOKEN, 'hubId:', hid);

const SERVER = {
  host: '0.peerjs.com',
  port: 443,
  path: '/',
};

const ICE = {
  config: { iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ]}
};

if (args.hub) {
  // ── Hub ──
  const peer = new Peer(hid, { ...SERVER, ...ICE });
  peer.on('open', (id) => {
    console.log('[HUB] OPEN:', id);
  });
  peer.on('connection', (conn) => {
    console.log('[HUB] incoming connection from:', conn.peer);
    conn.on('open', () => {
      console.log('[HUB] data connection open');
      conn.send(JSON.stringify({ type: 'peer-list', peers: [] }));
      console.log('[HUB] sent peer list');
    });
    conn.on('data', (d) => {
      const s = typeof d === 'string' ? d : new TextDecoder().decode(d);
      console.log('[HUB] data:', s);
    });
    conn.on('close', () => console.log('[HUB] conn closed'));
    conn.on('error', (e) => console.log('[HUB] conn err:', e.message));
  });
  peer.on('error', (e) => {
    console.log('[HUB] ERR:', e.type, '-', e.message);
    if (e.type === PeerErrorType.UnavailableID) {
      console.log('[HUB] ID taken, switching to peer mode...');
      peer.destroy();
      runPeer(peer, hid);
    }
  });
  console.log('[HUB] waiting...');
} else {
  runPeer(hid);
}

function runPeer(existingPeer, hid) {
  const peer = existingPeer || new Peer({ ...SERVER, ...ICE });
  peer.on('open', (id) => {
    console.log('[PEER] OPEN:', id);
    console.log('[PEER] connecting to hub:', hid);
    const conn = peer.connect(hid, { reliable: true, metadata: { nick: 'TestPeer' } });
    conn.on('open', () => {
      console.log('[PEER] connection to hub OPEN');
      conn.send('Hello from peer!');
    });
    conn.on('data', (d) => {
      const s = typeof d === 'string' ? d : new TextDecoder().decode(d);
      console.log('[PEER] data:', s);
      try { const j = JSON.parse(s); if (j.type === 'peer-list') console.log('[PEER] got peer-list:', j.peers); } catch {}
    });
    conn.on('close', () => console.log('[PEER] conn closed'));
    conn.on('error', (e) => console.log('[PEER] conn err:', e.message));
  });
  peer.on('connection', (conn) => {
    console.log('[PEER] incoming connection from:', conn.peer);
  });
  peer.on('error', (e) => console.log('[PEER] ERR:', e.type, '-', e.message));
}

setTimeout(() => { console.log('TIMEOUT - exiting'); process.exit(1); }, 30000);
