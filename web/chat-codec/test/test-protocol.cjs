/**
 * test-protocol.cjs — Tests for the WebRTC protocol layer
 *
 * Tests frame serialization, protocol message handling,
 * and peer discovery logic in isolation (no WebRTC needed).
 */
const assert = require('assert');

/* ── Import the relevant functions from webrtc.js ── */
// We inline the core logic under test

// ── Test helpers ──
let tests = 0, passed = 0;
function test(name, fn) {
  tests++;
  try { fn(); passed++; console.log('  ✅', name); }
  catch(e) { console.log('  ❌', name, '-', e.message); }
}

// ── Frame header format test ──
function makeFrame(msgId, dataLen, capacity, payload) {
  const buf = new Uint8Array(16 + payload.length);
  const dv = new DataView(buf.buffer, 0, 16);
  dv.setBigUint64(0, msgId, true);
  dv.setUint32(8, dataLen, true);
  dv.setUint32(12, capacity, true);
  buf.set(payload, 16);
  return buf;
}

function parseFrame(buf) {
  if (buf.length < 16) return null;
  const dv = new DataView(buf.buffer, buf.byteOffset, 16);
  return {
    msgId: dv.getBigUint64(0, true),
    dataLen: dv.getUint32(8, true),
    capacity: dv.getUint32(12, true),
    payload: buf.slice(16),
  };
}

test('Frame header format - roundtrip', () => {
  const payload = new Uint8Array([1,2,3,4]);
  const f = makeFrame(42n, 100, 5, payload);
  assert.strictEqual(f.length, 20);
  const p = parseFrame(f);
  assert.strictEqual(p.msgId, 42n);
  assert.strictEqual(p.dataLen, 100);
  assert.strictEqual(p.capacity, 5);
  assert.deepStrictEqual([...p.payload], [1,2,3,4]);
});

test('Frame too short returns null', () => {
  assert.strictEqual(parseFrame(new Uint8Array(10)), null);
});

// ── Protocol message parsing test ──
// Simulates what arrives via PeerJS data connection
// with different serialization modes

// Handler that processes incoming data (inlined from _setupConn / _forwardFrame logic)
function makeDataHandler(onPeerList, onFrame) {
  return function handleData(data, peerId) {
    // This mirrors _setupConn's conn.on('data', ...)
    if (typeof data === 'string') {
      // Could be JSON sent as string (JSON serialization)
      tryParseAndDispatch(data, peerId, onPeerList, onFrame);
      return;
    }
    // Convert to Uint8Array
    const buf = data instanceof ArrayBuffer ? new Uint8Array(data)
              : data instanceof Uint8Array ? data
              : new Uint8Array(data);
    if (buf.length < 2) {
      // Too short for JSON - forward as frame
      if (onFrame) onFrame(peerId, buf);
      return;
    }
    // Try to parse as JSON protocol message
    const str = new TextDecoder().decode(buf);
    try {
      const msg = JSON.parse(str);
      if (msg && msg.type === 'peer-list' && Array.isArray(msg.peers)) {
        if (onPeerList) onPeerList(msg.peers);
        return;
      }
      // Other JSON protocol messages could go here
      return;
    } catch (_) {
      // Not JSON - forward as coded frame
      if (onFrame) onFrame(peerId, buf);
    }
  };
}

function tryParseAndDispatch(str, peerId, onPeerList, onFrame) {
  try {
    const msg = JSON.parse(str);
    if (msg && msg.type === 'peer-list' && Array.isArray(msg.peers)) {
      if (onPeerList) onPeerList(msg.peers);
      return;
    }
  } catch (_) {
    // Not JSON, treat as frame... but strings typically aren't coded frames
    if (onFrame) onFrame(peerId, new TextEncoder().encode(str));
  }
}

// Encode string to Uint8Array (simulates binary-utf8 serialization)
function strToBinary(s) {
  return new TextEncoder().encode(s);
}

// Encode object to Uint8Array (simulates PeerJS binary serialization of an object)
function objToBinary(obj) {
  return new TextEncoder().encode(JSON.stringify(obj));
}

test('String protocol message (JSON serialization)', () => {
  let receivedPeers = null;
  const handler = makeDataHandler((peers) => { receivedPeers = peers; });
  
  handler(JSON.stringify({ type: 'peer-list', peers: [{ id: 'peer1', nick: 'Alice' }] }), 'sender1');
  assert.deepStrictEqual(receivedPeers, [{ id: 'peer1', nick: 'Alice' }]);
});

test('Binary protocol message (binary-utf8 serialization, stringified)', () => {
  let receivedPeers = null;
  const handler = makeDataHandler((peers) => { receivedPeers = peers; });
  
  // Simulates: conn.send(JSON.stringify(...)) with binary-utf8 serializer
  const binary = strToBinary(JSON.stringify({ type: 'peer-list', peers: [{ id: 'peer2', nick: 'Bob' }] }));
  handler(binary.buffer, 'sender2');
  assert.deepStrictEqual(receivedPeers, [{ id: 'peer2', nick: 'Bob' }]);
});

test('Binary protocol message (binary-utf8 serialization, object)', () => {
  let receivedPeers = null;
  const handler = makeDataHandler((peers) => { receivedPeers = peers; });
  
  // Simulates: conn.send({ type: 'peer-list', peers: [...] }) with binary-utf8 serializer
  const binary = objToBinary({ type: 'peer-list', peers: [{ id: 'peer3', nick: 'Charlie' }] });
  handler(binary, 'sender3');
  assert.deepStrictEqual(receivedPeers, [{ id: 'peer3', nick: 'Charlie' }]);
});

test('Binary coded frame (not JSON) forwarded correctly', () => {
  let framePeer = null, frameData = null;
  const handler = makeDataHandler(null, (peerId, data) => { framePeer = peerId; frameData = data; });
  
  // A coded frame with random binary data
  const frame = new Uint8Array([0xA3, 0x1B, 0xFF, 0x00, 0x42, 0x88]);
  handler(frame, 'coder1');
  assert.strictEqual(framePeer, 'coder1');
  assert.deepStrictEqual([...frameData], [0xA3, 0x1B, 0xFF, 0x00, 0x42, 0x88]);
});

test('Binary coded frame that starts with JSON-like byte is NOT mistaken', () => {
  let isFrame = false, isProtocol = false;
  const handler = makeDataHandler(
    () => { isProtocol = true; },
    () => { isFrame = true; }
  );
  
  // A coded frame starting with '{' (0x7B) but NOT valid JSON
  const frame = new Uint8Array([0x7B, 0x00, 0xFF, 0x1A, 0xBB, 0xCC]); // '{' + non-JSON
  handler(frame, 'coder2');
  assert.strictEqual(isFrame, true, 'Should be treated as frame');
  assert.strictEqual(isProtocol, false, 'Should NOT be treated as protocol message');
});

test('Binary coded frame that IS coincidentally valid JSON but not peer-list', () => {
  let isFrame = false, isProtocol = false;
  const handler = makeDataHandler(
    () => { isProtocol = true; },
    () => { isFrame = true; }
  );
  
  // A frame that happens to be valid JSON but not our protocol (type is different)
  const frame = strToBinary(JSON.stringify({ type: 'coded-frame', data: [1,2,3] }));
  handler(frame, 'coder3');
  assert.strictEqual(isFrame, false, 'Valid JSON should be consumed');
  assert.strictEqual(isProtocol, false, 'JSON without peer-list type is not our protocol');
  // This is acceptable - valid JSON is consumed, but not processed as peer-list
  // In reality, fountain codes won't produce valid JSON
});

test('Uint8Array vs ArrayBuffer both work', () => {
  let receivedPeers = null;
  const handler = makeDataHandler((peers) => { receivedPeers = peers; });
  
  const payload = { type: 'peer-list', peers: [] };
  const buf = objToBinary(payload);
  
  // As Uint8Array
  receivedPeers = null;
  handler(buf, 'p1');
  assert.deepStrictEqual(receivedPeers, []);
  
  // As ArrayBuffer
  receivedPeers = null;
  handler(buf.buffer, 'p2');
  assert.deepStrictEqual(receivedPeers, []);
});

test('Empty peer list', () => {
  let receivedPeers = 'NOT_SET';
  const handler = makeDataHandler((peers) => { receivedPeers = peers; });
  
  handler(strToBinary(JSON.stringify({ type: 'peer-list', peers: [] })), 'sender');
  assert.deepStrictEqual(receivedPeers, []);
});

// ── MESH LOGIC TESTS (no WebRTC) ──

// Simulate hub's _sendPeerList logic
function buildPeerList(hubConns, remoteId) {
  return Array.from(hubConns.keys())
    .filter(p => p !== remoteId)
    .map(id => ({ id, nick: hubConns.get(id) || id.slice(0, 8) }));
}

test('Peer list excludes the recipient', () => {
  const conns = new Map([
    ['alice', 'Alice'],
    ['bob', 'Bob'],
    ['charlie', 'Charlie'],
  ]);
  const list = buildPeerList(conns, 'bob');
  assert.strictEqual(list.length, 2);
  assert.strictEqual(list[0].id, 'alice');
  assert.strictEqual(list[1].id, 'charlie');
});

test('Peer list with only 2 peers is empty for new peer', () => {
  const conns = new Map([['alice', 'Alice']]);
  const list = buildPeerList(conns, 'alice');
  assert.strictEqual(list.length, 0);
});

test('Peer list with 0 peers is empty', () => {
  const conns = new Map();
  const list = buildPeerList(conns, 'alice');
  assert.strictEqual(list.length, 0);
});

// ── STATS ──
console.log(`\n📊 ${passed}/${tests} tests passed`);
process.exit(passed === tests ? 0 : 1);
