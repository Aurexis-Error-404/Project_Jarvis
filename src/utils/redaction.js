/**
 * Frontend mirror of backend/ai/security.py redaction patterns.
 *
 * Keep the regex list in sync with the Python one — when you change either
 * file, update the other in the same commit. The backend scrubs logs and
 * persisted jarvis.json; this module scrubs anything about to be written
 * to localStorage (reports, conversations) or logged to the browser console.
 */
const REDACTED = '[REDACTED]';

const PATTERNS = [
  // Google / Gemini API keys.
  { re: /\bAIza[0-9A-Za-z_\-]{30,48}\b/g, repl: REDACTED },
  // Anthropic / Claude keys.
  { re: /\bsk-ant-[A-Za-z0-9_\-]{80,}\b/g, repl: REDACTED },
  // OpenAI (classic + project-scoped).
  { re: /\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b/g, repl: REDACTED },
  // Groq.
  { re: /\bgsk_[A-Za-z0-9]{40,}\b/g, repl: REDACTED },
  // GitHub tokens.
  { re: /\bghp_[A-Za-z0-9]{36}\b/g, repl: REDACTED },
  { re: /\bgithub_pat_[A-Za-z0-9_]{60,}\b/g, repl: REDACTED },
  // AWS access key ID.
  { re: /\bAKIA[0-9A-Z]{16}\b/g, repl: REDACTED },
  // JWT (three base64url segments joined by dots, header starts with eyJ).
  { re: /\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b/g, repl: REDACTED },
];

// Assignment-style matches ("api_key: value", "TOKEN=value") need a callback
// so we can swap out just the value and keep the key name intact.
const ASSIGNMENT_RE = /(\b(?:api[_-]?key|secret|token|password|passwd|authorization|bearer)\s*[:=]\s*['"]?)([A-Za-z0-9_\-\.]{12,})(['"]?)/gi;

export function redactKeys(text) {
  if (typeof text !== 'string' || !text) return text;
  let out = text;
  for (const { re, repl } of PATTERNS) {
    out = out.replace(re, repl);
  }
  out = out.replace(ASSIGNMENT_RE, (_m, prefix, _val, suffix) => `${prefix}${REDACTED}${suffix}`);
  return out;
}

export function sanitizeForStorage(value) {
  if (typeof value === 'string') return redactKeys(value);
  if (Array.isArray(value)) return value.map(sanitizeForStorage);
  if (value && typeof value === 'object') {
    const out = {};
    for (const k of Object.keys(value)) out[k] = sanitizeForStorage(value[k]);
    return out;
  }
  return value;
}
