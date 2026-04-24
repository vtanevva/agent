import {CORE_BACKEND_URL} from '../config/api';

/**
 * Projects with client metadata, optional project_context, and recent tasks
 * (GET /debug/sql/projects-overview). ``userId`` is required to scope to that login + linked email.
 */
export async function fetchSqliteProjectsOverview(tasksPerProject = 30, userId) {
  const n = Math.min(100, Math.max(1, Number(tasksPerProject) || 30));
  const uid = String(userId || '').trim();
  if (!uid) {
    throw new Error('user_id is required to load your projects');
  }
  const q = new URLSearchParams();
  q.set('tasks_per_project', String(n));
  q.set('user_id', uid);
  const r = await fetch(
    `${CORE_BACKEND_URL}/debug/sql/projects-overview?${q.toString()}`
  );
  const ct = r.headers.get('content-type') || '';
  if (!r.ok) {
    let detail = '';
    try {
      if (ct.includes('application/json')) {
        const j = await r.json();
        detail = j?.error || JSON.stringify(j);
      } else {
        detail = (await r.text()).slice(0, 200);
      }
    } catch {
      detail = '';
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  if (!ct.includes('application/json')) {
    throw new Error('Unexpected response from server');
  }
  const data = await r.json();
  return Array.isArray(data.projects) ? data.projects : [];
}
