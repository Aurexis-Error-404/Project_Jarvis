// preload.js — Secure bridge between Electron main process and React renderer
// Uses contextBridge.exposeInMainWorld — NEVER expose ipcRenderer directly

const { contextBridge, ipcRenderer, shell } = require('electron');

/**
 * Expose a safe 'jarvis' API on window.jarvis
 * Only specific channels are whitelisted — no arbitrary IPC access
 */
contextBridge.exposeInMainWorld('jarvis', {
  /**
   * Register a callback for when the overlay is toggled open via Ctrl+Space.
   * Used by the renderer to focus the input field.
   * @param {Function} callback - Called when overlay is toggled open
   * @returns {Function} cleanup - Call to remove the listener
   */
  onToggleOverlay: (callback) => {
    const handler = (_event) => callback();
    ipcRenderer.on('toggle-overlay', handler);
    // Return cleanup function so React can unsubscribe in useEffect
    return () => {
      ipcRenderer.removeListener('toggle-overlay', handler);
    };
  },

  /**
   * Open a URL in the system default browser.
   * Safe alternative to shell.openExternal that doesn't require nodeIntegration.
   * @param {string} url - URL to open
   */
  openExternal: (url) => {
    // Validate URL before opening — only http/https allowed
    try {
      const parsed = new URL(url);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        shell.openExternal(url);
      } else {
        console.warn('[JARVIS] Blocked non-http URL:', url);
      }
    } catch (e) {
      console.warn('[JARVIS] Invalid URL:', url);
    }
  },
});

console.log('[JARVIS] Preload script loaded — window.jarvis API available');
