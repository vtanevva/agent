import {CORE_BACKEND_URL} from '../config/api';

/**
 * Projects with client metadata, optional project_context, and recent tasks
 * (GET /debug/sql/projects-overview).
 */
export async function fetchSqliteProjectsOverview(tasksPerProject = 30) {
  const n = Math.min(100, Math.max(1, Number(tasksPerProject) || 30));
  const r = await fetch(
    `${CORE_BACKEND_URL}/debug/sql/projects-overview?tasks_per_project=${encodeURIComponent(String(n))}`
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
