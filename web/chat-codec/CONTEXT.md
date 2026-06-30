---
type: Context
title: chat-codec
description: P2P chat with codec-share fountain codes + WebRTC mesh
tags: [project, chat, webrtc, wasm]
---

# chat-codec

**P2P encrypted chat** — message fountain-coded via [codec-share](https://github.com/lcmonteiro/codec-share) (WASM), transported over WebRTC mesh (PeerJS), with no server storing messages.

## Architecture

```
User types message
    → codec.share istream.split() → N coded frames
    → distributed round‑robin across 4 parallel DataChannels per peer
    → peer receives → codec.share ostream.push() → ostream.get() → decoded
```

## Key Files

| File | Role |
|---|---|
| `public/index.html` | UI (join screen + chat) |
| `public/app.js` | Glue between UI, codec, WebRTC |
| `public/codec.js` | WASM bridge or JS identity fallback |
| `public/webrtc.js` | WebRTC mesh via PeerJS |
| `wasm/codec_wrapper.cpp` | Emscripten wrapper (istream/ostream API) |
| `wasm/codec-share/` | Git submodule — codec-share headers |
| `wasm/build.sh` | WASM build script (requires Emscripten) |

## Building WASM

```bash
# In Codespace (Linux) with Emscripten installed:
cd web/chat-codec && bash wasm/build.sh
```

Without WASM, `codec.js` falls back to a JS identity codec.

## Conventiones

- Submodule `codec-share` em `wasm/codec-share/`
- Ficheiros estáticos em `public/` (GitHub Pages root)
- WASM output (gerado) em `public/` — gitignored
