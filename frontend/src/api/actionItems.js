import {CORE_BACKEND_URL} from '../config/api';
import {extractEmailAddress} from '../utils/emailParse';

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
/** Display name or local-part from a From header or bare email. */
export function senderShortName(from) {
  if (!from) return '';
  const m = /^([^<]+)<[^>]+>$/.exec(from);
  if (m && m[1]) return m[1].trim().replace(/(^"|"$)/g, '');
  const at = from.indexOf('@');
  if (at > 0) return from.slice(0, at);
  return from;
}

/**
 * Short visible seed for Quick Chat + hidden `reply_draft` payload for the model (snippet, etc.).
 */
export function buildReplyDraftNavParams(item) {
  if (!item) return {seedPrompt: '', replyDraft: null};
  const from = String(item.from || '').trim();
  const email = extractEmailAddress(from);
  const displayTarget = email || senderShortName(from) || 'the sender';
  const src = String(item.source || '').toLowerCase();
  const sourceLabel =
    src === 'gmail' ? 'Gmail' : src === 'slack' ? 'Slack' : src ? src.charAt(0).toUpperCase() + src.slice(1) : 'Message';
  const seedPrompt = `Draft a concise, warm, professional reply to ${displayTarget}. Source: ${sourceLabel}.`;
  const tid =
    item.gmailThreadId != null && String(item.gmailThreadId).trim()
      ? String(item.gmailThreadId).trim()
      : item.threadId != null && String(item.threadId).trim()
        ? String(item.threadId).trim()
        : null;
  const replyDraft = {
    thread_id: tid,
    source: item.source || '',
    subject: item.title || '',
    from_header: from,
    reply_to_email: email || '',
    snippet: String(item.snippet || '').slice(0, 4000),
  };
  return {seedPrompt, replyDraft};
}

export function mapActionItemToUi(item) {
  if (!item) return null;
  // Prefer source_id (unique per Gmail message / Slack event), then threadId, then a
  // source+timestamp fallback. threadId alone is shared by all replies in a thread, so
  // using it as a React key caused "same key" warnings on Home.
  const srcPrefix = String(item.source || 'x');
  const id = String(
    item.source_id
      ? `${srcPrefix}-${item.source_id}`
      : item.threadId
      ? `${srcPrefix}-${item.threadId}`
      : `${srcPrefix}-${item.ts || ''}`
  );
  const title =
    (item.subject && String(item.subject).trim()) ||
    (item.snippet && String(item.snippet).trim()) ||
    '(Untitled)';
  const fromAddr = String(item.from || '').trim();
  const timestamp = item.created_at || item.ts || '';
  const gt = item.gmailThreadId != null && String(item.gmailThreadId).trim() ? String(item.gmailThreadId).trim() : null;
  const cls = item.classification || {};
  const normalizedDue =
    cls && typeof cls.normalized_due === 'object' && cls.normalized_due
      ? cls.normalized_due.iso || ''
      : '';
  const due =
    item.due_datetime ||
    cls.due_datetime ||
    cls.due_datetime_iso ||
    normalizedDue ||
    null;
  return {
    id,
    threadId: item.threadId || null,
    gmailThreadId: gt,
    source: item.source || '',
    taskId: item.task_id != null ? item.task_id : null,
    title,
    from: fromAddr,
    snippet: String(item.snippet || ''),
    createdAt: timestamp,
    dueDatetime: due,
    classification: cls,
    classificationType: item.classification_type || '',
  };
}
