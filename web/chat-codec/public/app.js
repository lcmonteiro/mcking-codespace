/* ─── app.js — Main application logic ─────────────────────
 *
 * Glue between UI, codec (WASM), and WebRTC (mesh).
 *
 * Flow:
 *   1. User enters token + nickname → join room
 *   2. Hub discovery via deterministic PeerJS ID
 *   3. Hub sends peer list → mesh forms
 *   4. Outgoing: text → codec.encode() → broadcast frames
 *   5. Incoming: frames → codec.feed() → decode → display
 */

(function () {
  'use strict';

  const state = { token:'', nick:'Anonymous', mesh:null, codec:null, inRoom:false };

  /* ─── DOM refs ──────────────────────────────────────── */
  const $ = id => document.getElementById(id);
  const sJoin  = $('screen-join'),  sChat  = $('screen-chat');
  const iToken = $('room-token'),   iNick  = $('nickname');
  const bJoin  = $('btn-join'),     bGen   = $('btn-generate');
  const bLeave = $('btn-leave'),    bSend  = $('btn-send');
  const iMsg   = $('msg-input'),    elMsgs = $('messages');
  const dRoom  = $('room-display'), dPeers = $('peer-count');
  const dStat  = $('status-text'),  dCodec = $('codec-status');
  const dNick  = $('user-nick-display');

  /* ─── Init codec (WASM or fallback) ─────────────────── */

  (async () => {
    state.codec = new CodecBridge();
    await state.codec.init();
    dCodec.textContent = state.codec._fallback ? '⚡ JS fallback' : '🟢 WASM';
  })();

  /* ─── Random token ──────────────────────────────────── */

  bGen.addEventListener('click', () => { iToken.value = randomToken(); });

  /* ─── Join ──────────────────────────────────────────── */

  bJoin.addEventListener('click', onJoin);
  iToken.addEventListener('keydown', e => { if (e.key === 'Enter') onJoin(); });
  iNick.addEventListener('keydown',  e => { if (e.key === 'Enter') onJoin(); });

  async function onJoin() {
    const token = iToken.value.trim();
    const nick  = iNick.value.trim() || 'Anonymous';
    if (!token) return toast('Enter a room token', 'error');

    state.token = token;
    state.nick  = nick;
    bJoin.disabled = true;
    dStat.textContent = 'Connecting…';

    try {
      await joinRoom(token, nick);
      enterChat();
    } catch (e) {
      console.error('[app] join:', e);
      toast('Failed: ' + e.message, 'error');
      dStat.textContent = 'Error';
      bJoin.disabled = false;
    }
  }

  async function joinRoom(token, nick) {
    const mesh = new ChatMesh();

    mesh.onFrame = (msgId, frameData) => onFrame(msgId, frameData);

    mesh.onPeerJoin = (pid, label) => {
      dPeers.textContent = mesh.conns.size + ' peer' + (mesh.conns.size !== 1 ? 's' : '');
      removeSysMsg('Waiting for peers');
    };

    mesh.onPeerLeave = () => {
      dPeers.textContent = mesh.conns.size + ' peer' + (mesh.conns.size !== 1 ? 's' : '');
    };

    /* When we get a peer list from hub, connect to all of them */
    mesh._onPeerList = (peers) => {
      console.log('[app] Mesh peers:', peers);
      toast('Connected to ' + peers.length + ' peer' + (peers.length !== 1 ? 's' : ''), 'success');
      mesh.connectToPeers(peers);
    };

    state.mesh = mesh;
    return mesh.createPeer(nick, token);
  }

  /* ─── Enter chat ────────────────────────────────────── */

  function enterChat() {
    sJoin.classList.remove('active');
    sChat.classList.add('active');
    state.inRoom = true;

    dRoom.textContent = state.token;
    dNick.textContent = '👤 ' + state.nick;
    dStat.textContent = state.mesh.isHub ? '🟢 Room creator' : '🟢 Connected';
    bSend.disabled = false;
    iMsg.focus();

    addSystemMsg('🔐 Room: ' + state.token + ' — ' +
      (state.mesh.isHub ? 'you created it' : 'joined'));
    addSystemMsg('📡 Waiting for peers…');
  }

  /* ─── Send ──────────────────────────────────────────── */

  bSend.addEventListener('click', onSend);
  iMsg.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
  });
  iMsg.addEventListener('input', () => {
    iMsg.style.height = 'auto';
    iMsg.style.height = Math.min(iMsg.scrollHeight, 120) + 'px';
  });

  async function onSend() {
    const text = iMsg.value.trim();
    if (!text || !state.inRoom || !state.codec?.ready) return;
    iMsg.value = ''; iMsg.style.height = 'auto';

    const msgId  = state.mesh.nextMsgId();
    const frames = state.codec.encode(text, state.token);
    if (!frames.length) return toast('Encode failed', 'error');

    for (const f of frames) state.mesh.broadcast(msgId, f);

    addOutgoing(text);
    addSystemMsg(`📤 ${frames.length} frame${frames.length > 1 ? 's' : ''}`);
  }

  /* ─── Incoming frame ────────────────────────────────── */

  function onFrame(msgId, frameData) {
    if (!state.codec?.ready) return;

    state.codec.feed(msgId, frameData, state.token);

    const result = state.codec.tryDecode(msgId);
    if (result) {
      addIncoming(result.text, 'Peer');
      addSystemMsg(`📥 Decoded (${result.frameCount} frames)`);
    }
  }

  /* ─── Helpers ───────────────────────────────────────── */

  function removeSysMsg(text) {
    const items = elMsgs.querySelectorAll('.msg.system');
    for (const el of items) {
      if (el.textContent.includes(text)) el.remove();
    }
  }

  function addOutgoing(t) { appendMsg(t, state.nick, true); }
  function addIncoming(t, s) { appendMsg(t, s, false); }

  function appendMsg(text, sender, outgoing) {
    const div = document.createElement('div');
    div.className = 'msg ' + (outgoing ? 'outgoing' : 'incoming');

    const time = document.createElement('span');
    time.className = 'time';
    time.textContent = fmtTime(Date.now());
    div.appendChild(time);

    if (!outgoing) {
      const s = document.createElement('span');
      s.className = 'sender';
      s.textContent = sender;
      div.appendChild(s);
    }

    const body = document.createElement('span');
    body.textContent = text;
    div.insertBefore(body, time);

    elMsgs.appendChild(div);
    div.scrollIntoView({ behavior:'smooth' });
  }

  /* ─── Leave ──────────────────────────────────────────── */

  bLeave.addEventListener('click', leave);

  function leave() {
    state.inRoom = false;
    if (state.mesh) { state.mesh.disconnect(); state.mesh = null; }
    elMsgs.innerHTML = '<div class="msg system">Left the room.</div>';
    sChat.classList.remove('active');
    sJoin.classList.add('active');
    bJoin.disabled = false;
    bSend.disabled = true;
    dStat.textContent = '';
    dPeers.textContent = '0 peers';
    toast('Left the room', 'info');
  }

})();
