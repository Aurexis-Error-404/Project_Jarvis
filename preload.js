// preload.js — Secure bridge between Electron main process and React renderer
// Uses contextBridge.exposeInMainWorld — NEVER expose ipcRenderer directly

const { contextBridge, ipcRenderer, shell } = require('electron');
const path = require('path');

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
   * Open a native OS directory picker and return the selected path.
   * @returns {Promise<string|null>} selected path or null if cancelled
   */
  selectProjectDir: () => ipcRenderer.invoke('select-project-dir'),

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

  /**
   * Open a generated HTML report with the OS default browser.
   * Allowlist: must be inside the project's reports/ directory AND end with .html.
   * Returns a Promise — resolves on success, rejects with an Error on blocked/failed opens.
   * @param {string} filePath - Absolute path to the report file
   * @returns {Promise<void>}
   */
  openLocalFile: (filePath) => {
    return new Promise((resolve, reject) => {
      if (typeof filePath !== 'string' || filePath.length === 0) {
        const msg = 'openLocalFile: invalid path argument';
        console.warn('[JARVIS]', msg, filePath);
        return reject(new Error(msg));
      }

      const normalized = path.resolve(filePath);
      // Allowlist: must be inside {cwd}/reports/ and be an .html file
      const reportsBase = path.resolve(process.cwd(), 'reports');
      const isInsideReports = normalized.startsWith(reportsBase + path.sep) ||
                              normalized.startsWith(reportsBase + '/');
      const isHtml = normalized.toLowerCase().endsWith('.html');

      if (!isInsideReports || !isHtml) {
        const msg = `openLocalFile blocked — path must be .html inside reports/: ${normalized}`;
        console.warn('[JARVIS]', msg);
        return reject(new Error(msg));
      }

      shell.openPath(normalized).then((errMsg) => {
        if (errMsg) {
          console.warn('[JARVIS] openLocalFile OS error:', errMsg);
          reject(new Error(errMsg));
        } else {
          resolve();
        }
      });
    });
  },
});

console.log('[JARVIS] Preload script loaded — window.jarvis API available');
