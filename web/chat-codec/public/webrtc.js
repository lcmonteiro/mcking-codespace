/* ─── webrtc.js — WebRTC mesh via PeerJS ──────────────────
 *
 * Mesh with room discovery via deterministic "hub" peer ID.
 * Hub = first joiner. Others connect to hub, get peer list, mesh.
 *
 * Parallel DataChannels for coded frames (unreliable, unordered).
 * Transport frame: [msgId 8B][dataLen 4B LE][capacity 4B LE][codec_payload...]
 * JSON messages (peer-list) sent on the reliable channel.
 */

const CHANNEL_COUNT = 4;
const HUB_PREFIX    = 'cschat';

function hubId(token) {
  const h = hashSeed(token);
  /* toString(36) = [0-9a-z], safe for PeerJS */
  return HUB_PREFIX + h.toString(36).substring(0, 12);
}

class ChatMesh {
  constructor() {
    this.peer       = null;
    this.myId       = null;
    this.nick       = 'Anonymous';
    this.token      = '';
    this.isHub      = false;
    this.conns      = new Map();   /* peerId → ConnWrapper */
    this.onFrame    = null;        /* cb(msgId, frameData) */
    this.onPeerJoin = null;
    this.onPeerLeave= null;
    this._onPeerList= null;        /* cb(peers) — set by app */
    this._msgCounter= 0n;
  }

  /* ─── Create/Join room ──────────────────────────────── */

  async createPeer(nick, token) {
    this.nick  = nick || 'Anonymous';
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
        console.log('[webrtc] Hub created:', id);
        resolve(id);
      });

      peer.on('connection', (conn) => this._handleConn(conn));

      peer.on('error', (err) => {
        if (err.type === 'unavailable-id') {
          peer.destroy();
          this._joinAsPeer(nick, token, hid, resolve, reject);
        } else {
          reject(err);
        }
      });

      setTimeout(() => { if (!this.myId) { peer.destroy(); reject(new Error('Timeout')); } }, 15000);
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
      console.log('[webrtc] Peer joined:', id);
      const conn = peer.connect(hid, {
        reliable: true,
        metadata: { nick: this.nick, type:'join-request' }
      });
      /* Setup but don't fire onPeerJoin yet — wait for open */
      this._setupConn(conn, hid, 'Hub');
      resolve(id);
    });

    peer.on('connection', (conn) => this._handleConn(conn));
    peer.on('error', (err) => reject(err));
  }

  /* ── Incoming connection wrapper ────────────────────── */

  _handleConn(conn) {
    const meta = conn.metadata || {};
    const label = meta.nick || conn.peer.slice(0, 8);
    this._setupConn(conn, conn.peer, label);
  }

  /* ── Setup a single peer connection ─────────────────── */

  _setupConn(conn, peerId, label) {
    if (this.conns.has(peerId)) return;

    const wrapper = {
      conn, peerId, label,
      channels: [],      /* parallel DataChannels */
      _jsonBuf: '',      /* for fragmented JSON reassembly */
    };
    this.conns.set(peerId, wrapper);

    conn.on('open', () => {
      console.log('[webrtc] Conn open:', peerId, label);
      this._createParallelChannels(conn, peerId, wrapper);
      if (this.onPeerJoin) this.onPeerJoin(peerId, label);
      /* Hub sends peer list to newcomer */
      if (this.isHub) this._sendPeerList(peerId);
    });

    conn.on('data', (data) => {
      /* String → JSON protocol */
      if (typeof data === 'string') {
        this._handleProtocolMsg(data, peerId);
        return;
      }
      /* Binary → coded frame */
      this._forwardFrame(data, peerId);
    });

    conn.on('close', () => {
      console.log('[webrtc] Conn closed:', peerId);
      this.conns.delete(peerId);
      if (this.onPeerLeave) this.onPeerLeave(peerId);
    });

    conn.on('error', (err) => console.warn('[webrtc] Conn err:', peerId, err.message));
  }

  /* ── Handle JSON protocol messages ──────────────────── */

  _handleProtocolMsg(jsonStr, peerId) {
    try {
      const msg = JSON.parse(jsonStr);
      if (msg.type === 'peer-list' && Array.isArray(msg.peers)) {
        console.log('[webrtc] Received peer list:', msg.peers);
        if (this._onPeerList) this._onPeerList(msg.peers);
      }
    } catch (_) {}
  }

  /* ── Forward binary frame to app ────────────────────── */

  _forwardFrame(data, peerId) {
    if (!this.onFrame) return;
    try {
      const buf = data instanceof ArrayBuffer ? new Uint8Array(data)
                : data instanceof Uint8Array    ? data
                : new Uint8Array(data);
      /* Format: [msgId 8B][dataLen 4B LE][capacity 4B LE][payload...] */
      if (buf.length < 16) {
        console.warn('[webrtc] _forwardFrame: too short:', buf.length, 'from', peerId);
        return;
      }
      const dv = new DataView(buf.buffer, buf.byteOffset, 16);
      const msgId = dv.getBigUint64(0, true);
      const dataLen = dv.getUint32(8, true);
      const capacity = dv.getUint32(12, true);
      const payload = buf.slice(16);
      console.log('[webrtc] RECV frame: from=', peerId, 'msgId=', msgId,
                  'payloadLen=', payload.length, 'capacity=', capacity,
                  'dataLen=', dataLen, 'totalLen=', buf.length);
      this.onFrame(msgId, payload, capacity, dataLen);
    } catch (e) {
      console.warn('[webrtc] _forwardFrame error:', e.message);
    }
  }

  /* ── Parallel DataChannels ──────────────────────────── */

  _createParallelChannels(conn, peerId, wrapper) {
    const pc = conn._peerConnection;
    if (!pc) return;

    for (let i = 0; i < CHANNEL_COUNT; i++) {
      try {
        const dc = pc.createDataChannel(`cs-${i}`, {
          ordered: false, maxRetransmits: 0
        });
        dc.binaryType = 'arraybuffer';
        dc.onmessage  = (ev) => this._forwardFrame(ev.data, peerId);
        wrapper.channels.push(dc);
      } catch (_) {}
    }

    pc.ondatachannel = (ev) => {
      const dc = ev.channel;
      if (!dc.label.startsWith('cs-')) return;
      dc.binaryType = 'arraybuffer';
      dc.onmessage  = (ev) => this._forwardFrame(ev.data, peerId);
      wrapper.channels.push(dc);
    };
  }

  /* ── Send peer list to newcomer ─────────────────────── */

  _sendPeerList(remoteId) {
    const peers = Array.from(this.conns.keys())
      .filter(p => p !== remoteId)
      .map(id => ({ id, nick: this.conns.get(id)?.label || id.slice(0, 8) }));
    const wrapper = this.conns.get(remoteId);
    if (wrapper && wrapper.conn?.open) {
      wrapper.conn.send(JSON.stringify({ type: 'peer-list', peers }));
    }
  }

  /* ── Broadcast coded frames for a message ────────────── */

  broadcast(msgId, frames, capacity, dataLen) {
    if (this.conns.size === 0) {
      console.warn('[webrtc] broadcast: no connections');
      return;
    }
    if (!Number.isInteger(capacity) || capacity < 1) capacity = 32;
    if (!Number.isInteger(dataLen) || dataLen < 0) dataLen = 0;

    console.log('[webrtc] SEND: msgId=', msgId, 'frames=', frames.length,
                'capacity=', capacity, 'dataLen=', dataLen,
                'conns=', this.conns.size);

    for (let fi = 0; fi < frames.length; fi++) {
      const frameData = frames[fi];
      /* Transport format: [msgId 8B][dataLen 4B LE][capacity 4B LE][payload...] */
      const buf = new Uint8Array(16 + frameData.length);
      const dv = new DataView(buf.buffer, 0, 16);
      dv.setBigUint64(0, msgId, true);
      dv.setUint32(8, dataLen, true);
      dv.setUint32(12, capacity, true);
      buf.set(frameData, 16);

      let sentCount = 0;
      for (const [pid, w] of this.conns) {
        const chs = w.channels.filter(dc => dc.readyState === 'open');
        if (chs.length > 0) {
          try {
            const dc = chs[Number(msgId % BigInt(chs.length))];
            dc.send(buf.buffer);
            sentCount++;
          } catch (e) {
            console.warn('[webrtc] parallel send fail to', pid, ':', e.message);
          }
        } else if (w.conn?.open) {
          try {
            w.conn.send(buf.buffer);
            sentCount++;
          } catch (e) {
            console.warn('[webrtc] reliable send fail to', pid, ':', e.message);
          }
        } else {
          console.warn('[webrtc] no open channel for', pid);
        }
      }
      if (fi === 0 || fi === frames.length - 1) {
        console.log('[webrtc] frame', fi, '/', frames.length,
                    'sent to', sentCount, 'peers, len=', frameData.length);
      }
    }
  }

  /* ── Connect to additional mesh peers (from peer list) ── */

  connectToPeers(peers) {
    for (const p of peers) {
      if (p.id === this.myId || this.conns.has(p.id)) continue;
      console.log('[webrtc] Connecting to mesh peer:', p.id);
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

window.ChatMesh = ChatMesh;
window.hubId    = hubId;
