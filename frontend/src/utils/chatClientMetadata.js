/**
 * Optional client hints for POST /api/chat (deadlines, meetings) in the user's zone.
 */
export function buildChatMetadata() {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz && typeof tz === 'string' && tz.trim()) {
      return {timezone: tz.trim()};
    }
  } catch {
    // ignore
  }
  return null;
}
