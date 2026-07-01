/**
 * test-hub-only.cjs — Creates a PeerJS hub, logs everything
 * Usage: node test-hub-only.cjs <token>
 * 
 * Leave running, then in another terminal:
 *   node test-peer-only.cjs <token>
 */
const wrtc = require('@roamhq/wrtc');
globalThis.window = globalThis;
globalThis.RTCPeerConnection    = wrtc.RTCPeerConnection;
globalThis.RTCSessionDescription = wrtc.RTCSessionDescription;
globalThis.RTCIceCandidate      = wrtc.RTCIceCandidate;
globalThis.MediaStream          = wrtc.MediaStream;

const { Peer } = require('peerjs');

function hashSeed(s) { let h1=0x811c9dc5,h2=0x6c62272e; for(let i=0;i<s.length;i++){const c=s.charCodeAt(i);h1^=c;h1=Math.imul(h1,0x01000193);h2^=c;h2=Math.imul(h2,0x01dfcd6d);} return (BigInt(h1)<<32n)|BigInt(h2>>>0); }
const token = process.argv[2] || 'TESTTOKEN123';
const hid = 'cschat' + hashSeed(token).toString(36).substring(0, 12);
console.log('TOKEN:', token);
console.log('HUBID:', hid);

const hub = new Peer(hid, {
  host: '0.peerjs.com', port: 443, path: '/',
  config: { iceServers: [{urls: 'stun:stun.l.google.com:19302'}] }
});
hub.on('open', (id) => console.log('[HUB] OPEN:', id));
hub.on('connection', (conn) => {
  console.log('[HUB] INCOMING CONN from:', conn.peer, 'meta:', JSON.stringify(conn.metadata));
  conn.on('open', () => {
    console.log('[HUB] CONN OPEN with', conn.peer);
    conn.send(JSON.stringify({ type: 'peer-list', peers: [] }));
    console.log('[HUB] Sent peer-list to', conn.peer);
  });
  conn.on('data', (d) => {
    const s = typeof d === 'string' ? d : Buffer.from(d).toString();
    console.log('[HUB] DATA from', conn.peer, ':', s);
  });
  conn.on('close', () => console.log('[HUB] CONN CLOSED:', conn.peer));
  conn.on('error', (e) => console.log('[HUB] CONN ERR:', conn.peer, e.message));
});
hub.on('error', (e) => console.log('[HUB] ERR:', e.type, '-', e.message));
hub.on('disconnected', () => console.log('[HUB] DISCONNECTED from signaling server'));
