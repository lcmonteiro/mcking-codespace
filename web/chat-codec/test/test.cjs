/**
 * test.cjs — Test codec-share WASM encode/decode pipeline
 *
 * Usage: node test.cjs
 */
const path = require('path');
const WASM_DIR = path.join(__dirname, '..', 'public');
globalThis.window = globalThis;
const CodecShare = require(path.join(WASM_DIR, 'codec_share.js'));

function hashSeed(str) {
  let h1 = 0x811c9dc5, h2 = 0x6c62272e;
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    h1 ^= c; h1 = Math.imul(h1, 0x01000193);
    h2 ^= c; h2 = Math.imul(h2, 0x01dfcd6d);
  }
  return (BigInt(h1) << 32n) | BigInt(h2 >>> 0);
}

(async () => {
  const mod = await CodecShare({
    locateFile: f => path.join(WASM_DIR, f), onAbort: () => {},
  });
  console.log('✅ WASM loaded, ping:', mod._ping());

  const token = 'test-token';
  const h = hashSeed(token);
  const lo = Number(h & 0xFFFFFFFFn) >>> 0;
  const hi = Number((h >> 32n) & 0xFFFFFFFFn) >>> 0;
  const FS = 64;
  const lenPtr = mod._malloc(4);

  function testEncodeDecode(label, text) {
    const bytes = Buffer.from(text);
    if (bytes.length === 0) {
      console.log(`  ✅ ${label}: (0B, skip)`);
      return true;
    }

    /* ── Encoder ── */
    const eid = mod._create_encoder();
    const inPtr = mod._malloc(bytes.length);
    mod.HEAPU8.set(bytes, inPtr);
    const count = mod._enc_set(eid, inPtr, bytes.length, lo, hi, FS);
    mod._free(inPtr);
    if (count <= 0) { mod._destroy_encoder(eid); return false; }

    const capacity = Math.floor((count - 3) / 2);
    const frames = [];
    for (let i = 0; i < count; i++) {
      mod.setValue(lenPtr, 0, 'i32');
      const ptr = mod._enc_get(eid, lenPtr);
      const flen = mod.getValue(lenPtr, 'i32');
      if (!ptr || flen <= 0) break;
      frames.push(Buffer.from(mod.HEAPU8.subarray(ptr, ptr + flen)));
    }
    mod._destroy_encoder(eid);

    /* ── Decoder ── */
    const did = mod._create_decoder();
    mod._dec_create(did, capacity, bytes.length, lo, hi);

    let ok = false;
    for (let i = 0; i < frames.length && !ok; i++) {
      const fp = mod._malloc(frames[i].length);
      mod.HEAPU8.set(frames[i], fp);
      const st = mod._dec_set(did, fp, frames[i].length);
      mod._free(fp);

      if (st > 0) {
        mod.setValue(lenPtr, 0, 'i32');
        const outPtr = mod._dec_get(did, lenPtr);
        const outLen = mod.getValue(lenPtr, 'i32');
        if (outLen === bytes.length) {
          ok = Buffer.from(mod.HEAPU8.subarray(outPtr, outPtr + outLen)).equals(bytes);
        }
        mod._mem_free(outPtr);
        break;
      } else if (st === -1) {
        console.log(`  ❌ ${label}: dec_set error:`, mod.UTF8ToString(mod._last_error()));
        return false;
      }
    }
    mod._destroy_decoder(did);

    console.log(`  ${ok ? '✅' : '❌'} ${label}: (${bytes.length}B, ${frames.length} frames, ${ok ? bytes.length + 'B OK' : 'FAIL'})`);
    return ok;
  }

  const tests = [
    ['short msg',  'Ola'],
    ['hello',      'Hello World'],
    ['100 A',      'A'.repeat(100)],
    ['255 B',      'B'.repeat(255)],
    ['256 C',      'C'.repeat(256)],
    ['500 D',      'D'.repeat(500)],
    ['1000 E',     'E'.repeat(1000)],
    ['5000 F',     'F'.repeat(5000)],
    ['utf-8',      'Olá! Como estás? ' + '😊'.repeat(5)],
    ['binary',     Buffer.from([0x00,0x01,0x02,0xFF,0xFE,0x80,0x7F]).toString('binary')],
    ['empty',      ''],
  ];

  let passed = 0;
  for (const [label, text] of tests) {
    if (testEncodeDecode(label, text)) passed++;
  }

  mod._free(lenPtr);
  console.log(`\n📊 ${passed} passed, ${tests.length - passed} failed`);
  process.exit(passed === tests.length ? 0 : 1);
})();
