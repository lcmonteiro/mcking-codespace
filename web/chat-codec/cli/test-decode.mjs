/**
 * test-decode.mjs — Test WASM codec encode → decode round-trip
 *
 * Tests both small messages (1 block) and large (multi-block).
 * Now uses the fixed WASM that bypasses broken ostream verification.
 */
import path from 'path';
import { createRequire } from 'module';

const __dirname = import.meta.dirname;
const require = createRequire(import.meta.url);

globalThis.window = globalThis;

const WASM_DIR = path.join(__dirname, '..', 'public');

async function loadWasm() {
  const CodecShare = require(path.join(WASM_DIR, 'codec_share.js'));
  const mod = await CodecShare({
    locateFile: (file) => path.join(WASM_DIR, file),
    onAbort: (msg) => {},
  });
  return mod;
}

function strToBytes(s) { return Buffer.from(s, 'utf-8'); }
function bytesToStr(b) { return b.toString('utf-8'); }

function hashSeed(str) {
  let h1 = 0x811c9dc5, h2 = 0x6c62272e;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 ^= c; h1 = Math.imul(h1, 0x01000193);
    h2 ^= c; h2 = Math.imul(h2, 0x01dfcd6d);
  }
  return (BigInt(h1) << 32n) | BigInt(h2 >>> 0);
}

function tokenParts(s) {
  const h = hashSeed(String(s));
  return { lo: Number(h & 0xFFFFFFFFn) >>> 0, hi: Number((h >> 32n) & 0xFFFFFFFFn) >>> 0 };
}

async function roundtrip(mod, msg, label) {
  const token = 'test-token-42';
  const { lo, hi } = tokenParts(token);
  const FS = 64;

  // Encode
  const inBytes = strToBytes(msg);
  const inPtr = mod._malloc(inBytes.length);
  mod.HEAPU8.set(inBytes, inPtr);
  const count = mod._enc_begin(inPtr, inBytes.length, lo, hi, FS);
  mod._free(inPtr);

  if (count <= 0) {
    console.log(`  ❌ ${label}: encode failed`);
    return false;
  }

  const frames = [];
  const lenPtr = mod._malloc(4);
  for (let i = 0; i < count; i++) {
    mod.setValue(lenPtr, 0, 'i32');
    const ptr = mod._enc_next(lenPtr);
    const len = mod.getValue(lenPtr, 'i32');
    if (!ptr || len <= 0) break;
    frames.push(Buffer.from(mod.HEAPU8.subarray(ptr, ptr + len)));
  }
  mod._free(lenPtr);
  mod._enc_reset();

  // Compute expected capacity from enc_begin return.
  // enc_begin returns (K+1)*2+3. capacity = K+1 = (count - 3) / 2
  const expectedCap = Math.floor((count - 3) / 2);
  const useCap = Math.max(expectedCap, 1);
  mod._dec_create(useCap, lo, hi);

  let decoded = null;
  for (let i = 0; i < frames.length; i++) {
    const fptr = mod._malloc(frames[i].length);
    mod.HEAPU8.set(frames[i], fptr);
    const status = mod._dec_feed(fptr, frames[i].length);
    mod._free(fptr);

    if (status > 0) {
      const lptr = mod._malloc(4);
      const outPtr = mod._dec_get(lptr);
      const outLen = mod.getValue(lptr, 'i32');
      decoded = bytesToStr(Buffer.from(mod.HEAPU8.subarray(outPtr, outPtr + outLen)));
      mod._mem_free(outPtr);
      mod._free(lptr);
      mod._dec_reset();
      break;
    }
  }

  if (decoded === msg) {
    console.log(`  ✅ ${label}: (${msg.length}B, ${frames.length} frames, ${decoded.length}B out) SUCCESS`);
    return true;
  } else {
    console.log(`  ❌ ${label}: MISMATCH`);
    if (decoded) {
      console.log(`     expected(${msg.length}): ${msg.substring(0, 40)}...`);
      console.log(`     got(${decoded.length}):      ${decoded.substring(0, 40)}...`);
    } else {
      console.log('     got: null (decode incomplete)');
    }
    return false;
  }
}

async function main() {
  const mod = await loadWasm();
  console.log('✅ WASM loaded, ping:', mod._ping());

  let pass = 0, fail = 0;

  // Test 1: Short message (fits in 1 frame)
  if (await roundtrip(mod, 'Olá!', 'short msg')) pass++; else fail++;
  if (await roundtrip(mod, 'Hello World', 'hello')) pass++; else fail++;

  // Test 2: Medium message (2-3 frames)
  if (await roundtrip(mod, 'A'.repeat(100), '100 A')) pass++; else fail++;

  // Test 3: Large message (many frames)
  if (await roundtrip(mod, 'B'.repeat(500), '500 B')) pass++; else fail++;

  // Test 4: Portuguese text
  if (await roundtrip(mod, 'A minha terra é a Maia, no Porto, Portugal! ☀️', 'portuguese')) pass++; else fail++;

  // Test 5: Edge case - empty?
  try {
    if (await roundtrip(mod, '', 'empty')) pass++; else fail++;
  } catch (e) {
    console.log('  ⚠️ empty message:', e.message);
    fail++;
  }

  console.log(`\n📊 ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
