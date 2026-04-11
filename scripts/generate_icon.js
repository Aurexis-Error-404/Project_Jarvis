// generate_icon.js — Creates a proper 16x16 PNG tray icon for JARVIS
// Run: node scripts/generate_icon.js

const fs = require('fs');
const path = require('path');

// Minimal valid 16x16 PNG with a cyan "J" shape on dark background
// Created by building the PNG binary manually (no dependencies needed)

function createPNG(width, height, pixels) {
  // PNG signature
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

  // IHDR chunk
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;  // bit depth
  ihdr[9] = 6;  // color type: RGBA
  ihdr[10] = 0; // compression
  ihdr[11] = 0; // filter
  ihdr[12] = 0; // interlace

  // Build raw pixel data with filter bytes
  const rawData = [];
  for (let y = 0; y < height; y++) {
    rawData.push(0); // filter: none
    for (let x = 0; x < width; x++) {
      const idx = (y * width + x) * 4;
      rawData.push(pixels[idx], pixels[idx + 1], pixels[idx + 2], pixels[idx + 3]);
    }
  }

  // Compress with zlib (built-in)
  const zlib = require('zlib');
  const compressed = zlib.deflateSync(Buffer.from(rawData));

  // Build chunks
  function makeChunk(type, data) {
    const typeBuffer = Buffer.from(type);
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length, 0);
    const crcData = Buffer.concat([typeBuffer, data]);
    const crc = Buffer.alloc(4);
    crc.writeInt32BE(crc32(crcData), 0);
    return Buffer.concat([length, typeBuffer, data, crc]);
  }

  // CRC32 implementation
  function crc32(buf) {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < buf.length; i++) {
      c ^= buf[i];
      for (let j = 0; j < 8; j++) {
        c = (c >>> 1) ^ (c & 1 ? 0xEDB88320 : 0);
      }
    }
    return (c ^ 0xFFFFFFFF) | 0;
  }

  const ihdrChunk = makeChunk('IHDR', ihdr);
  const idatChunk = makeChunk('IDAT', compressed);
  const iendChunk = makeChunk('IEND', Buffer.alloc(0));

  return Buffer.concat([signature, ihdrChunk, idatChunk, iendChunk]);
}

// Draw a 16x16 icon: cyan circle with dark background
const size = 16;
const pixels = new Uint8Array(size * size * 4);

for (let y = 0; y < size; y++) {
  for (let x = 0; x < size; x++) {
    const idx = (y * size + x) * 4;
    const cx = x - 7.5;
    const cy = y - 7.5;
    const dist = Math.sqrt(cx * cx + cy * cy);

    if (dist < 7) {
      // Dark background circle
      pixels[idx] = 26;     // R
      pixels[idx + 1] = 26; // G
      pixels[idx + 2] = 46; // B (#1a1a2e)
      pixels[idx + 3] = 255;

      // Draw a "J" letter in cyan
      const inJ = (
        // Top bar of J (row 3-4, col 4-11)
        (y >= 3 && y <= 4 && x >= 5 && x <= 11) ||
        // Vertical bar (col 8-9, row 3-10)
        (x >= 8 && x <= 9 && y >= 3 && y <= 10) ||
        // Bottom curve (row 10-12, col 4-9)
        (y >= 10 && y <= 11 && x >= 5 && x <= 9) ||
        // Left hook (col 4-5, row 9-11)
        (x >= 5 && x <= 6 && y >= 9 && y <= 11)
      );

      if (inJ) {
        pixels[idx] = 0;      // R
        pixels[idx + 1] = 212; // G
        pixels[idx + 2] = 255; // B (#00d4ff)
        pixels[idx + 3] = 255;
      }
    } else {
      // Transparent outside circle
      pixels[idx] = 0;
      pixels[idx + 1] = 0;
      pixels[idx + 2] = 0;
      pixels[idx + 3] = 0;
    }
  }
}

const png = createPNG(size, size, pixels);
const outputPath = path.join(__dirname, '..', 'assets', 'icon.png');
fs.writeFileSync(outputPath, png);
console.log(`[JARVIS] Tray icon written to ${outputPath} (${png.length} bytes)`);
