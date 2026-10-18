import { locale } from './i18n.js';
import { nativeHeaders, serverOrigin } from './native.js';

/**
 * Event stream client for StackPad backend SSE.
 * Automatically handles reconnection, backoff, visibility pause, and polling fallback.
 */
export function connectEvents({
  topics = ['services', 'settings', 'alert', 'progress'],
  onEvent,
  onConnectedChange,
  onFallbackChange,
}) {
  let controller = null;
  let retryTimer = null;
  let fallbackTimer = null;
  let disposed = false;
  let consecutiveFailures = 0;
  let isFallback = false;
  let isConnected = false;

  const BACKOFF_DELAYS = [1000, 2000, 5000, 10000];

  function setConnected(val) {
    if (isConnected !== val) {
      isConnected = val;
      onConnectedChange?.(val);
    }
  }

  function setFallback(val) {
    if (isFallback !== val) {
      isFallback = val;
      onFallbackChange?.(val);
    }
  }

  async function connect() {
    if (disposed || document.visibilityState === 'hidden') return;
    cleanupStream();

    controller = new AbortController();
    const query = topics.length ? `?topics=${topics.join(',')}` : '';
    const url = `${serverOrigin()}/api/events${query}`;

    try {
      const headers = {
        'Accept': 'text/event-stream',
        'X-StackPad-Lang': locale,
        ...await nativeHeaders(),
      };

      const response = await fetch(url, {
        method: 'GET',
        headers,
        credentials: 'same-origin',
        signal: controller.signal,
      });

      if (!response.ok) {
        if ([404, 405, 500, 501, 502, 503].includes(response.status)) {
          consecutiveFailures = 3;
          setFallback(true);
        }
        throw new Error(`HTTP ${response.status}`);
      }

      setConnected(true);
      consecutiveFailures = 0;
      setFallback(false);

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let receivedCount = 0;

      while (!disposed) {
        const { value, done } = await reader.read();
        if (done) break;
        receivedCount++;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const rawBlock of parts) {
          const lines = rawBlock.split('\n');
          let currentEvent = 'message';
          let currentData = '';

          for (const line of lines) {
            if (line.startsWith(':')) {
              // Comment or ping/connected
              continue;
            }
            if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              const content = line.slice(5).trim();
              currentData = currentData ? currentData + '\n' + content : content;
            }
          }

          if (currentData) {
            try {
              const parsed = JSON.parse(currentData);
              onEvent?.(currentEvent, parsed);
            } catch (err) {
              console.warn('Failed to parse SSE event data', err);
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError' || disposed) {
        return;
      }
      console.warn('Events stream error:', err);
    } finally {
      setConnected(false);
      scheduleRetry();
    }
  }

  function scheduleRetry() {
    if (disposed || document.visibilityState === 'hidden') return;

    consecutiveFailures++;
    if (consecutiveFailures >= 3) {
      setFallback(true);
      // In fallback mode, retry SSE once every 60 seconds
      clearTimeout(fallbackTimer);
      fallbackTimer = setTimeout(() => {
        if (!disposed && document.visibilityState !== 'hidden') {
          connect();
        }
      }, 60000);
      return;
    }

    const delay = BACKOFF_DELAYS[Math.min(consecutiveFailures - 1, BACKOFF_DELAYS.length - 1)];
    clearTimeout(retryTimer);
    retryTimer = setTimeout(() => {
      if (!disposed && document.visibilityState !== 'hidden') {
        connect();
      }
    }, delay);
  }

  function cleanupStream() {
    if (controller) {
      controller.abort();
      controller = null;
    }
    clearTimeout(retryTimer);
    retryTimer = null;
    clearTimeout(fallbackTimer);
    fallbackTimer = null;
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'hidden') {
      cleanupStream();
      setConnected(false);
    } else {
      // Reconnect immediately when visible
      consecutiveFailures = 0;
      connect();
    }
  }

  document.addEventListener('visibilitychange', onVisibilityChange);
  connect();

  return () => {
    disposed = true;
    document.removeEventListener('visibilitychange', onVisibilityChange);
    cleanupStream();
    setConnected(false);
  };
}
