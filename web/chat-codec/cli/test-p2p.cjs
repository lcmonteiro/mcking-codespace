/**
 * test-p2p.cjs — Two-peer connection test
 * Usage: node test-p2p.cjs [--token X]
 *
 * Creates a hub, waits, then connects as a peer.
 */
const wrtc = require('@roamhq/wrtc');
globalThis.window = globalThis;
globalThis.RTCPeerConnection    = wrtc.RTCPeerConnection;
globalThis.RTCSessionDescription = wrtc.RTCSessionDescription;
globalThis.RTCIceCandidate      = wrtc.RTCIceCandidate;
globalThis.MediaStream          = wrtc.MediaStream;

const { Peer } = require('peerjs');

function hashSeed(s) { let h1=0x811c9dc5,h2=0x6c62272e; for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);h1^=c;h1=Math.imul(h1,0x01000193);h2^=c;h2=Math.imul(h2,0x01dfcd6d);} return (BigInt(h1)<<32n)|BigInt(h2>>>0); }
const token = process.argv[2] || ('test-' + Date.now().toString(36));
const hid = 'cschat' + hashSeed(token).toString(36).substring(0, 12);
console.log('=== P2P Test ===');
console.log('token:', token);
console.log('hubId:', hid);

const ICE = { config: { iceServers: [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
]}};

const SERVER = { host: '0.peerjs.com', port: 443, path: '/' };

let connected = false;

// ── Hub ──
const hub = new Peer(hid, { ...SERVER, ...ICE });
hub.on('open', (id) => {
  console.log('[HUB] OPEN:', id);
  
  // Now connect as peer
  const p = new Peer({ ...SERVER, ...ICE });
  p.on('open', (pid) => {
    console.log('[PEER] OPEN:', pid);
    console.log('[PEER] Connecting to hub...');
    const conn = p.connect(hid, { reliable: true, metadata: { nick: 'test' } });
    conn.on('open', () => {
      console.log('[PEER] CONN OPEN! ✅');
      conn.send(JSON.stringify({ type: 'test', msg: 'Hello' }));
      connected = true;
    });
    conn.on('data', (d) => {
      const s = typeof d === 'string' ? d : new TextDecoder().decode(d);
      console.log('[PEER] data:', s);
      try { const j = JSON.parse(s); if (j.type === 'peer-list') console.log('[PEER] peers:', j.peers); } catch {}
    });
    conn.on('error', (e) => console.log('[PEER] conn err:', e.message));
  });
  p.on('connection', (c) => console.log('[PEER] incoming conn:', c.peer));
  p.on('error', (e) => console.log('[PEER] err:', e.type, '-', e.message));
});

hub.on('connection', (conn) => {
  console.log('[HUB] incoming conn from:', conn.peer);
  conn.on('open', () => {
    console.log('[HUB] conn OPEN ✅');
    conn.send(JSON.stringify({ type: 'peer-list', peers: [] }));
  });
  conn.on('data', (d) => {
    const s = typeof d === 'string' ? d : new TextDecoder().decode(d);
    console.log('[HUB] data:', s);
  });
  conn.on('close', () => console.log('[HUB] conn closed'));
  conn.on('error', (e) => console.log('[HUB] conn err:', e.message));
});

hub.on('error', (e) => {
  console.log('[HUB] err:', e.type, '-', e.message);
  if (e.type === 'unavailable-id') {
    // Hub ID taken, we're not first — just wait
  }
});

// Wait and check
setTimeout(() => {
  if (connected) {
    console.log('\n✅ P2P CONNECTION SUCCESSFUL');
  } else {
    console.log('\n❌ P2P CONNECTION FAILED - timeout');
  }
  hub.destroy();
  process.exit(connected ? 0 : 1);
}, 15000);
