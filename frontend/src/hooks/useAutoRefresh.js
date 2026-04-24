import {useCallback, useEffect, useRef} from 'react';
import {useFocusEffect} from '@react-navigation/native';

import {onDataChange} from '../utils/dataEvents';

/**
 * Keeps a screen's data fresh without relying on pull-to-refresh.
 *
 * On every focused render the screen gets three signals, all routed through a
 * single ``loader`` callback:
 *   1. A one-shot call when the screen first focuses (replaces most existing
 *      ``useEffect`` + ``useFocusEffect`` loader wiring).
 *   2. A background ``setInterval`` poll at ``intervalMs`` (default 15s) so
 *      items that arrive asynchronously from the backend (new Gmail action
 *      items, Slack messages, meetings created server-side) appear on the
 *      screen the user is looking at without a manual refresh.
 *   3. A cross-screen "data-changed" event fired by other parts of the app
 *      (see ``utils/dataEvents.js``) — e.g. after the chat creates a task or
 *      project.
 *
 * The poll and subscription are torn down on blur/unmount so a backgrounded
 * screen never hits the network.
 *
 * ``loader`` is called with no arguments; pass a stable reference (via
 * ``useCallback``) so the interval is not rebuilt on every render.
 */
export function useAutoRefresh(loader, {intervalMs = 15000, enabled = true} = {}) {
  const loaderRef = useRef(loader);
  useEffect(() => {
    loaderRef.current = loader;
  }, [loader]);

  useFocusEffect(
    useCallback(() => {
      if (!enabled) return undefined;

      let cancelled = false;

      const run = () => {
        if (cancelled) return;
        try {
          const maybePromise = loaderRef.current?.();
          if (maybePromise && typeof maybePromise.catch === 'function') {
            maybePromise.catch(() => {
              // Loader-level error handling is the loader's job; we just make
              // sure a rejection doesn't break the interval.
            });
          }
        } catch {
          // see above
        }
      };

      run();

      const id = setInterval(run, Math.max(2000, Number(intervalMs) || 15000));
      const unsubscribe = onDataChange(() => run());

      return () => {
        cancelled = true;
        clearInterval(id);
        unsubscribe();
      };
    }, [enabled, intervalMs]),
  );
}

export default useAutoRefresh;
