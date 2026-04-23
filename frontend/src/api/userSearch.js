import {CORE_BACKEND_URL} from '../config/api';

/**
 * Search SQLite-backed user data: messages, tasks, projects, project notes, calendar.
 *
 * @param {{ userId?: string, q: string, limit?: number }} opts
 * @returns {Promise<{ success: boolean, hits: Record<string, any[]>, total?: number, tokens?: string[] }>}
 */
export async function fetchUserSearch({userId, q, limit = 20} = {}) {
  const params = new URLSearchParams({
    q: String(q || '').trim(),
    limit: String(Math.max(1, Math.min(40, Number(limit) || 20))),
  });
  if (userId) params.set('user_id', String(userId));
  const r = await fetch(`${CORE_BACKEND_URL}/api/search?${params}`, {
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
  return r.json();
}
