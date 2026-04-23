import {API_BASE_URL, CORE_BACKEND_URL} from '../config/api';
import {fetchSqliteTasks, mapSqliteRowToSchedulerTask} from './sqliteTasks';

export function toDateSafe(value) {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function normalizeTitleForMatch(title) {
  const s = String(title || '')
    .toLowerCase()
    .replace(/[\u2019']/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!s) return '';

  const stop = new Set([
    'attend',
    'meeting',
    'meet',
    'with',
    'call',
    'schedule',
    'needed',
    'due',
    'in',
    'the',
    'a',
    'an',
    'to',
    'for',
    'and',
    'on',
    'at',
    'reply',
    'follow',
    'up',
    'confirm',
  ]);
  return s
    .split(' ')
    .filter((w) => w && !stop.has(w))
    .join(' ')
    .trim();
}

function tokenSet(str) {
  const s = normalizeTitleForMatch(str);
  if (!s) return new Set();
  return new Set(s.split(' ').filter(Boolean));
}

function jaccard(aSet, bSet) {
  if (!aSet.size || !bSet.size) return 0;
  let inter = 0;
  for (const t of aSet) if (bSet.has(t)) inter += 1;
  const uni = aSet.size + bSet.size - inter;
  return uni ? inter / uni : 0;
}

function looksLikeGenericMeeting(text) {
  const s = String(text || '').toLowerCase();
  if (!s) return false;
  return /\b(meet|meeting|call|sync|catch up|chat|interview|demo)\b/.test(s);
}

/**
 * Merge Google Calendar events with pipeline-style tasks (due_datetime).
 * Matches SchedulerPage semantics (dedupe task vs meeting event).
 */
export function buildScheduleItems(events, tasks) {
  const items = [];
  const eventsByDay = new Map();

  for (const ev of events || []) {
    const start = toDateSafe(ev.start);
    if (!start) continue;
    const end = toDateSafe(ev.end) || start;
    const dayKey = start.toDateString();
    const list = eventsByDay.get(dayKey) || [];
    list.push({
      summary: ev.summary || '',
      tokens: tokenSet(ev.summary || ''),
      startMs: start.getTime(),
      endMs: end.getTime(),
    });
    eventsByDay.set(dayKey, list);
    items.push({
      kind: 'event',
      start,
      end,
      summary: ev.summary || '(Untitled event)',
      location: ev.location || '',
      description: ev.description || '',
      provider: ev.provider || '',
      html_link: ev.html_link || '',
      _raw: ev,
    });
  }

  for (const t of tasks || []) {
    const start = toDateSafe(t.due_datetime);
    if (!start) continue;

    const dayKey = start.toDateString();
    const dayEvents = eventsByDay.get(dayKey) || [];
    const taskTokens = tokenSet(t.title || '');
    const normTask = normalizeTitleForMatch(t.title || '');
    const taskLooksMeeting = looksLikeGenericMeeting(t.title) || looksLikeGenericMeeting(t.reason);
    const taskStartMs = start.getTime();
    const taskEndMs = taskStartMs + 90 * 60 * 1000;

    const looksDuplicate = dayEvents.some((ev) => {
      const startDiffMs = Math.abs((ev.startMs || 0) - taskStartMs);
      const overlaps =
        (ev.startMs != null && ev.endMs != null && taskStartMs < ev.endMs && taskEndMs > ev.startMs) ||
        startDiffMs <= 15 * 60 * 1000;

      const sim = jaccard(taskTokens, ev.tokens);
      if (sim >= 0.6) return true;
      const normEv = normalizeTitleForMatch(ev.summary || '');
      const titleMatch = !!normTask && !!normEv && (normTask.includes(normEv) || normEv.includes(normTask));

      if (overlaps) {
        if (sim >= 0.15) return true;
        if (titleMatch) return true;
        if (taskLooksMeeting && looksLikeGenericMeeting(ev.summary)) return true;
      }

      return titleMatch;
    });
    if (looksDuplicate) continue;

    const end = new Date(start.getTime() + 30 * 60 * 1000);
    items.push({
      kind: 'task',
      start,
      end,
      task_id: t._id,
      summary: t.title || '(Untitled task)',
      priority: t.priority || 'LATER',
      priority_score: t.priority_score || 0,
      reason: t.reason || '',
      source: t.source || '',
      _raw: t,
    });
  }

  items.sort((a, b) => a.start.getTime() - b.start.getTime());
  return items;
}

async function loadCalendarEvents(userId, {timeMin, timeMax} = {}) {
  const body = {
    user_id: userId,
    max_results: 250,
    ...(timeMin ? {time_min: timeMin} : {}),
    ...(timeMax ? {time_max: timeMax} : {}),
  };

  const bases = [...new Set([CORE_BACKEND_URL, API_BASE_URL].filter(Boolean))];

  for (const base of bases) {
    try {
      const r = await fetch(`${base}/api/calendar/events`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        continue;
      }
      if (data?.success && Array.isArray(data.events)) {
        const bannerUrl =
          data?.action === 'connect_google' && data?.connect_url ? data.connect_url : '';
        return {events: data.events, connectUrl: bannerUrl};
      }
      if (data?.action === 'connect_google' && data?.connect_url) {
        return {events: [], connectUrl: data.connect_url};
      }
    } catch {
      continue;
    }
  }
  return {events: [], connectUrl: ''};
}

async function loadTasksFromSqlite() {
  try {
    const rows = await fetchSqliteTasks(200);
    const all = rows.map((row) => mapSqliteRowToSchedulerTask(row)).filter(Boolean);
    const withDue = [];
    const withoutDue = [];
    for (const t of all) {
      if (t?.due_datetime) withDue.push(t);
      else withoutDue.push(t);
    }
    return {tasks: withDue, unscheduled: withoutDue};
  } catch {
    return {tasks: [], unscheduled: []};
  }
}

/**
 * @param {string} userId
 * @param {{ timeMin?: string, timeMax?: string }} [range] Optional ISO window for Google + SQLite calendar rows.
 */
export async function fetchScheduleSources(userId, range = {}) {
  const {timeMin, timeMax} = range || {};
  const [eventsRes, tasksRes] = await Promise.all([
    loadCalendarEvents(userId, {timeMin, timeMax}),
    loadTasksFromSqlite(),
  ]);
  return {
    events: eventsRes.events,
    connectUrl: eventsRes.connectUrl,
    tasks: tasksRes.tasks,
    unscheduled: tasksRes.unscheduled,
  };
}
