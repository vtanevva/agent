/**
 * Best-effort extract a single email address from a From / To header or plain string.
 */
export function extractEmailAddress(value) {
  if (value == null) return '';
  const s = String(value).trim();
  if (!s) return '';
  const angle = /<([^>]+)>/.exec(s);
  if (angle) {
    const inner = angle[1].trim();
    if (inner.includes('@')) return inner;
  }
  const loose = /[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/.exec(s);
  if (loose) return loose[0].trim();
  return '';
}
