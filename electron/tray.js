// electron/tray.js — System tray icon and context menu
// Extracted from main.js to keep main process lean.

const { Tray, Menu, nativeImage } = require('electron');
const path = require('path');

/**
 * Create the system tray icon with Open / Quit menu.
 *
 * @param {{ toggleOverlay: Function, onQuit: Function }} opts
 * @returns {Tray}
 */
function createTray({ toggleOverlay, onQuit }) {
  let icon;
  const iconPath = path.join(__dirname, '..', 'assets', 'icon.png');

  // Try file-based icon first
  try {
    const fileIcon = nativeImage.createFromPath(iconPath);
    if (!fileIcon.isEmpty()) {
      icon = fileIcon.resize({ width: 16, height: 16 });
      console.log('[JARVIS] Tray icon loaded from file');
    }
  } catch (e) {
    console.warn('[JARVIS] Failed to load icon file:', e.message);
  }

  // Fallback: programmatic 16x16 cyan dot
  if (!icon || icon.isEmpty()) {
    const size = 16;
    const buffer = Buffer.alloc(size * size * 4);
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const cx = x - 7.5, cy = y - 7.5;
        const dist = Math.sqrt(cx * cx + cy * cy);
        const idx = (y * size + x) * 4;
        if (dist < 6) {
          buffer[idx]     = 0;   // R
          buffer[idx + 1] = 212; // G
          buffer[idx + 2] = 255; // B
          buffer[idx + 3] = 255; // A
        }
      }
    }
    icon = nativeImage.createFromBuffer(buffer, { width: size, height: size });
    console.log('[JARVIS] Tray icon: using fallback');
  }

  const tray = new Tray(icon);
  tray.setToolTip('JARVIS — AI Developer Assistant');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open',
      click: toggleOverlay,
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: onQuit,
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', toggleOverlay);

  return tray;
}

module.exports = { createTray };
