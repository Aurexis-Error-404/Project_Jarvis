// electron/main.js — Electron main process
// Frameless, transparent, always-on-top JARVIS overlay
// Toggled by Ctrl+Space (fallback: Ctrl+Shift+Space), hidden by default, system tray icon

const { app, BrowserWindow, globalShortcut, ipcMain, dialog } = require('electron');
const path = require('path');
const { createTray } = require('./tray');

// ─── Redirect userData before anything else ───────────────
// Prevents "Access is denied" cache errors when the default
// %APPDATA%\jarvis directory has a permission/lock conflict.
app.setPath('userData', path.join(app.getPath('home'), '.jarvis-data'));

// Disable GPU shader disk cache — avoids the secondary cache
// error (gpu_disk_cache.cc:725) without affecting rendering.
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache');

// ─── Prevent multiple instances ──────────────────────────
// Must run before whenReady() to avoid globalShortcut crash
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

// ─── Globals ─────────────────────────────────────────────
let mainWindow = null;
let tray = null;
let isQuitting = false;

// ─── Window dimensions (Notebook UI) ───────────
const DEFAULT_WIDTH = 1280;
const DEFAULT_HEIGHT = 800;

/**
 * Create the main overlay window.
 * - Frameless, transparent, always-on-top
 * - Pre-rendered but hidden — toggle visibility only (< 100ms open time)
 * - Positioned at bottom-right of primary display
 * - contextIsolation: true, nodeIntegration: false — no exceptions
 */
function createWindow() {
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;

  mainWindow = new BrowserWindow({
    width: DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
    frame: false,
    transparent: true,
    alwaysOnTop: false,
    resizable: true,
    skipTaskbar: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,          // preload uses require('path') and shell — needs Node access
    },
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'src', 'index.html'));

  // Intercept close — hide only, real quit from tray
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.maximize();
    mainWindow.show();
    console.log('[JARVIS] Notebook window ready');
  });
}

/**
 * Toggle overlay visibility.
 * Pure show/hide — no heavy work, keeps open time < 100ms.
 */
function toggleOverlay() {
  if (!mainWindow) return;
  if (mainWindow.isVisible()) {
    mainWindow.hide();
  } else {
    mainWindow.show();
    mainWindow.focus();
    mainWindow.webContents.send('toggle-overlay');
  }
}

// ─── App lifecycle ───────────────────────────────────────
app.whenReady().then(() => {
  createWindow();

  tray = createTray({
    toggleOverlay,
    onQuit: () => {
      isQuitting = true;
      app.quit();
    },
  });

  // IPC: let renderer open a native directory picker
  ipcMain.handle('select-project-dir', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Select Project Directory',
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  });

  // Register global hotkey.
  // Ctrl+Space is reserved by Windows IME on some systems — fall back
  // to Ctrl+Shift+Space if the primary registration fails.
  const HOTKEYS = ['Ctrl+Space', 'Ctrl+Shift+Space'];
  const registeredKey = HOTKEYS.find((key) => globalShortcut.register(key, toggleOverlay));
  if (registeredKey) {
    console.log(`[JARVIS] Hotkey registered: ${registeredKey}`);
  } else {
    console.error('[JARVIS] Failed to register hotkey — toggle via tray icon');
  }
});

// Unregister hotkeys on quit to prevent leaks
app.on('will-quit', () => {
  try {
    globalShortcut.unregisterAll();
  } catch (_) {
    // Ignore — app may not have fully initialized
  }
});

// Handle second instance — focus existing window
app.on('second-instance', () => {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  }
});
