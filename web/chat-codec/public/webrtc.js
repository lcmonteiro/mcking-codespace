/* ─── webrtc.js — WebRTC mesh via PeerJS ──────────────────
 *
 * Mesh with room discovery via deterministic "hub" peer ID.
 * Hub = first joiner. Others connect to hub, get peer list, mesh.
 *
 * Parallel DataChannels for coded frames (unreliable, unordered).
 * Transport frame: [msgId (8B LE)][codec_payload...]
 * JSON messages (peer-list) sent on the reliable channel.
 */

const CHANNEL_COUNT = 4;
const HUB_PREFIX    = 'cschat-';

function hubId(token) {
  const h = hashSeed(token);
  return HUB_PREFIX + h.toString(36).substring(0, 10);
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
        reliable: true, serialization: 'binary',
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
      if (buf.length < 8) return;
      const view = new DataView(buf.buffer, buf.byteOffset, 8);
      const msgId = view.getBigUint64(0, true);
      this.onFrame(msgId, buf.slice(8));
    } catch (_) {}
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

  /* ── Broadcast a coded frame ────────────────────────── */

  broadcast(msgId, frameData) {
    if (this.conns.size === 0) return;
    const buf = new Uint8Array(8 + frameData.length);
    new DataView(buf.buffer, 0, 8).setBigUint64(0, msgId, true);
    buf.set(frameData, 8);

    for (const [pid, w] of this.conns) {
      const chs = w.channels.filter(dc => dc.readyState === 'open');
      if (chs.length > 0) {
        try { chs[Number(msgId % BigInt(chs.length))].send(buf.buffer); } catch (_) {}
      } else if (w.conn?.open) {
        try { w.conn.send(buf.buffer); } catch (_) {}
      }
    }
  }

  /* ── Connect to additional mesh peers (from peer list) ── */

  connectToPeers(peers) {
    for (const p of peers) {
      if (p.id === this.myId || this.conns.has(p.id)) continue;
      console.log('[webrtc] Connecting to mesh peer:', p.id);
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

window.ChatMesh = ChatMesh;
window.hubId    = hubId;
