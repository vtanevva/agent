/**
 * Lightweight pub/sub used to notify data-driven pages (Home, Tasks, Projects,
 * WeeklySchedule) that the server state may have changed and a refetch is in
 * order.
 *
 * Why not Redux / React Query? The app currently fetches each page's data with
 * plain hooks; adding a full state layer for one signal is overkill. A tiny
 * module-level Set of listeners works on both web and native and lets any page
 * opt in without wiring props through the navigation tree.
 *
 * Typical flow:
 *   - ``emitDataChange()`` is called after a chat turn that likely created a
 *     task, project, or meeting (see QuickChatPage / ChatPage).
 *   - Pages subscribe via ``onDataChange(fn)`` inside ``useAutoRefresh`` so
 *     their loaders fire immediately — no need to pull-to-refresh.
 */

const listeners = new Set();

export function emitDataChange(reason) {
  for (const fn of Array.from(listeners)) {
    try {
      fn(reason);
    } catch {
      // Subscribers must never break the emitter; failures are swallowed so one
      // bad listener can't poison the rest.
    }
  }
}

export function onDataChange(fn) {
  if (typeof fn !== 'function') return () => {};
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
