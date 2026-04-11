import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import bash from 'highlight.js/lib/languages/bash';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';

hljs.registerLanguage('python', python);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('css', css);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('jsx', javascript);

marked.setOptions({
  breaks: true,
  gfm: true,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
});

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote',
  'h1', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'a',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'span', 'div',
];

const ALLOWED_ATTR = ['href', 'target', 'rel', 'class'];

// Wrap CAUSE/FIX/ALSO CHECK sections in styled divs
function formatDiagnosis(html) {
  if (!html.includes('CAUSE:') || !html.includes('FIX:')) return html;
  return html
    .replace(/CAUSE:\s*/g, '<div class="diag-section diag-cause"><span class="diag-label">CAUSE</span> ')
    .replace(/FIX:\s*/g, '</div><div class="diag-section diag-fix"><span class="diag-label">FIX</span> ')
    .replace(/ALSO CHECK:\s*/g, '</div><div class="diag-section diag-check"><span class="diag-label">ALSO CHECK</span> ')
    + '</div>';
}

export default function renderMarkdown(text) {
  if (!text) return '';
  const raw = marked.parse(text);
  const clean = DOMPurify.sanitize(raw, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ADD_ATTR: ['target'],
  });
  return formatDiagnosis(clean);
}
