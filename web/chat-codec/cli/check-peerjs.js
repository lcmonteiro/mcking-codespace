// check-peerjs.js
const fs = require('fs');
const src = fs.readFileSync(require.resolve('peerjs'), 'utf8');

// Find default options
const hostMatch = src.match(/['"]host['"]\s*[=:]\s*['"]([^'"]+)/);
console.log('Default host:', hostMatch ? hostMatch[1] : 'not found');

const portMatch = src.match(/['"]port['"]\s*[=:]\s*(\d+)/);
console.log('Default port:', portMatch ? portMatch[1] : 'not found');

const pathMatch = src.match(/['"]path['"]\s*[=:]\s*['"]([^'"]+)/);
console.log('Default path:', pathMatch ? pathMatch[1] : 'not found');

// Look for the default server URL
const urlMatch = src.match(/['"]0\.peerjs\.com/);
console.log('Has 0.peerjs.com:', !!urlMatch);

// Check for signaling_server or something
const keyMatch = src.match(/peerjs.*server|signaling|cloud.*server/i);
console.log('Server ref:', keyMatch ? keyMatch[0] : 'not found');

// Check the package version
const pkg = require('peerjs/package.json');
console.log('PeerJS version:', pkg.version);
