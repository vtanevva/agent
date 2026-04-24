import {CORE_BACKEND_URL} from '../config/api';

/**
 * Local tasks for the signed-in user (GET /api/tasks with user_id).
 * Same data partition as projects / clients.
 */
export async function fetchSqliteTasks(limit = 200, userId) {
  const lim = Math.min(500, Math.max(1, Number(limit) || 200));
  const uid = String(userId || '').trim();
  if (!uid) {
    return [];
  }
  const q = new URLSearchParams();
  q.set('limit', String(lim));
  q.set('user_id', uid);
  const r = await fetch(`${CORE_BACKEND_URL}/api/tasks?${q.toString()}`);
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
  return Array.isArray(data.tasks) ? data.tasks : [];
}

function classificationObjectFromRow(row) {
  const raw = row?.classification_json ?? row?.classification;
  if (raw == null || raw === '') return {};
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw;
  if (typeof raw !== 'string') return {};
  try {
    const o = JSON.parse(raw);
    return o && typeof o === 'object' ? o : {};
  } catch {
    return {};
  }
}

/**
 * Shape a SQLite row like the legacy pipeline task objects used in the UI.
 */
export function mapSqliteTaskToUi(row) {
  if (!row) return null;
  const id = row.id != null ? String(row.id) : '';
  const ctype = String(row.classification_type || '').toUpperCase();
  let priority = 'LATER';
  if (/(URGENT|NOW|P0|IMMEDIATE)/.test(ctype)) {
    priority = 'NOW';
  } else if (/(SOON|P1|MEDIUM)/.test(ctype)) {
    priority = 'SOON';
  }

  const cls = classificationObjectFromRow(row);
  const dueDatetime = cls.due_datetime || cls.due_datetime_iso || null;

  const pipelineLike = {
    _id: id,
    title: row.title || '',
    status: 'pending',
    priority,
    priority_score: 0,
    reason: row.classification_type || '',
    source: row.source || 'sqlite',
    due_datetime: dueDatetime,
    created_at: row.created_at || '',
    actions: [],
  };

  return {
    id,
    text: row.title || '',
    status: 'todo',
    priority,
    priorityScore: 0,
    reason: row.classification_type || '',
    impact: 2,
    effort: 2,
    source: row.source || 'sqlite',
    meta: {
      description: row.classification_type || '',
      due_date: dueDatetime,
      source_ref: row.source_id || '',
      created_at: row.created_at || '',
      actions: [],
    },
    _taskData: pipelineLike,
    _sqlite: true,
  };
}

/** SchedulerPage expects pipeline-like objects with `_id` and optional `due_datetime`. */
export function mapSqliteRowToSchedulerTask(row) {
  const m = mapSqliteTaskToUi(row);
  if (!m) return null;
  const d = m._taskData;
  return {
    _id: d._id,
    title: d.title,
    due_datetime: d.due_datetime,
    priority: d.priority,
    priority_score: d.priority_score,
    reason: d.reason,
    source: d.source,
  };
}
