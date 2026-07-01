// find-peerjs-defaults.js
const fs = require('fs');
const src = fs.readFileSync(require.resolve('peerjs/dist/peerjs.js'), 'utf8');

// Find where the WebSocket URL is built
let idx = src.indexOf('wss');
if (idx > 0) {
  console.log('WS context:', src.substring(Math.max(0, idx - 100), idx + 200));
}

// Find the Socket class to see how it connects
idx = src.indexOf('class Socket');
if (idx > 0) {
  const sock = src.substring(idx, idx + 4000);
  const ctorMatch = sock.match(/constructor\s*\([^)]*\)\s*\{/);
  if (ctorMatch) {
    const ctorEnd = ctorMatch.index + ctorMatch[0].length;
    console.log('Socket ctor:', sock.substring(ctorEnd, ctorEnd + 300));
  }
}

// Find where CLOUD_HOST is used as default
idx = src.indexOf('CLOUD_HOST');
if (idx > 0) {
  // Find the property assignment
  const before = src.substring(Math.max(0, idx - 300), idx);
  const after = src.substring(idx, idx + 300);
  console.log('CLOUD_HOST context:', before.substring(before.length - 200), '---', after);
}

// Search for options merging
const optMatch = src.match(/options\s*=\s*Object\.assign[^;]+/);
if (optMatch) console.log('Options merge:', optMatch[0].substring(0, 200));
