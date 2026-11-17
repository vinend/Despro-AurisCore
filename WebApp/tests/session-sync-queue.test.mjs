import assert from "node:assert/strict";
import test from "node:test";
import { createSessionSyncQueue } from "../src/lib/auriscore/session-sync-queue.ts";

test("a recording queued during an upload is scanned without another online event", async () => {
  const request = createSessionSyncQueue();
  const started = Promise.withResolvers();
  const upload = Promise.withResolvers();
  const outbox = ["first"];
  const synced = [];
  let active = 0;
  const scan = async () => {
    assert.equal(++active, 1);
    const snapshot = outbox.splice(0);
    started.resolve();
    await upload.promise;
    synced.push(...snapshot);
    active--;
  };
  const first = request(scan);
  await started.promise;
  outbox.push("second");
  const second = request(scan);
  upload.resolve();
  await Promise.all([first, second]);
  assert.deepEqual(synced, ["first", "second"]);
});

test("account changes retain the newest scan and failures do not lock the queue", async () => {
  const request = createSessionSyncQueue();
  const started = Promise.withResolvers();
  const release = Promise.withResolvers();
  const seen = [];
  const first = request(async () => { started.resolve(); await release.promise; throw new Error("offline"); });
  await started.promise;
  request(async () => { seen.push("old-account"); });
  request(async () => { seen.push("current-account"); });
  release.resolve();
  await assert.rejects(first, /offline/);
  await request(async () => { seen.push("retry"); });
  assert.deepEqual(seen, ["current-account", "retry"]);
});
