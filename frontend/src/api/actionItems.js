import {CORE_BACKEND_URL} from '../config/api';

/**
 * Fetch unified action items from the core backend.
 * These are the messages that, in the old design, were shown as "Action Items":
 * Gmail / Slack items classified as actionable.
 *
 * Shape of each returned item (see backend/api/routes/action_items.py):
 *   {
 *     source, source_id, threadId, from, subject, snippet,
 *     channel, user, ts, created_at,
 *     classification_type, classification, has_action
 *   }
 */
export async function fetchActionItems(userId, limit = 100) {
  const params = new URLSearchParams({
    user_id: userId || '',
    limit: String(Math.max(1, Math.min(2000, Number(limit) || 100))),
  });
  const r = await fetch(`${CORE_BACKEND_URL}/api/action-items?${params}`, {
    method: 'GET',
    headers: {'Content-Type': 'application/json'},
  });
  const ct = r.headers.get('content-type') || '';
  const isJson = ct.includes('application/json');
  if (!r.ok) {
    let detail = '';
    try {
      detail = isJson ? JSON.stringify(await r.json()) : (await r.text()).slice(0, 200);
    } catch {
      detail = '';
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  if (!isJson) throw new Error('Unexpected response');
  const data = await r.json();
  return Array.isArray(data?.items) ? data.items : [];
}

/**
 * Mark an action item as done on the backend (currently a no-op but future-proof).
 */
export async function markActionItemDone({userId, threadId, source}) {
  if (!threadId) return;
  try {
    await fetch(`${CORE_BACKEND_URL}/api/action-items/done`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({user_id: userId, thread_id: threadId, source}),
    });
  } catch {
    // optimistic hide — the backend route is a no-op placeholder today
  }
}

/**
 * Normalise one raw API item into the shape the Home UI renders.
 */
export function mapActionItemToUi(item) {
  if (!item) return null;
  const id = String(item.threadId || item.source_id || `${item.source || 'x'}-${item.ts || ''}`);
  const title =
    (item.subject && String(item.subject).trim()) ||
    (item.snippet && String(item.snippet).trim()) ||
    '(Untitled)';
  const fromAddr = String(item.from || '').trim();
  const timestamp = item.created_at || item.ts || '';
  return {
    id,
    threadId: item.threadId || null,
    source: item.source || '',
    title,
    from: fromAddr,
    snippet: String(item.snippet || ''),
    createdAt: timestamp,
    classification: item.classification || {},
    classificationType: item.classification_type || '',
  };
}
