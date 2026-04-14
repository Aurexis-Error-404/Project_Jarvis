// src/constants/config.js — Frontend configuration values
// Centralises ports, URLs, and timing magic numbers.

// ─── WebSocket ────────────────────────────────────────────
export const WS_URL            = 'ws://localhost:8765';
export const RECONNECT_BASE_MS = 2_000;   // Initial backoff delay
export const RECONNECT_MAX_MS  = 30_000;  // Backoff cap

// ─── UI Timing ────────────────────────────────────────────
export const SPLASH_DISMISS_MS   = 1_500; // Auto-skip splash on connect
export const INPUT_FOCUS_MS      = 50;    // Delay before re-focusing input
export const SURFACE_DISMISS_MS  = 8_000; // Auto-dismiss proactive surface card
export const TOOL_DONE_REMOVE_MS = 1_500; // Remove completed tool indicators
