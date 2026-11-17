/** Serialize outbox scans, retaining the latest request made during a scan. */
export function createSessionSyncQueue() {
  let pending: (() => Promise<void>) | undefined;
  let active: Promise<void> | undefined;
  return (scan: () => Promise<void>): Promise<void> => {
    pending = scan;
    if (!active) {
      active = Promise.resolve().then(async () => {
        let failure: unknown;
        let failed = false;
        try {
          while (pending) {
            const next = pending;
            pending = undefined;
            try { await next(); }
            catch (error) { failure = error; failed = true; }
          }
        } finally { active = undefined; }
        if (failed) throw failure;
      });
    }
    return active;
  };
}
