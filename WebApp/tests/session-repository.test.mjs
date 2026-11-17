import assert from "node:assert/strict";
import test from "node:test";
import { sha256, syncSession } from "../src/lib/auriscore/session-repository.ts";

function clientFixture({ owner = "user-a", state = "ready", stored = new Blob(["wav-a"]) } = {}) {
  let uploads = 0, updates = 0;
  const record = { id: "session", user_id: "user-a", audio_path: "user-a/session.wav", audio_bytes: 5, sync_state: state };
  const database = {
    select: () => database,
    eq: () => database,
    maybeSingle: async () => ({ data: record, error: null }),
    update: () => { updates++; return database; },
    single: async () => ({ data: { ...record, sync_state: "ready" }, error: null }),
  };
  const client = {
    auth: { getUser: async () => ({ data: { user: { id: owner } }, error: null }) },
    from: () => database,
    storage: { from: () => ({
      upload: async () => { uploads++; return { error: { message: "Duplicate object" } }; },
      download: async () => ({ data: stored, error: null }),
    }) },
  };
  return { client, record, counts: () => ({ uploads, updates }) };
}

test("a completed session retry never reuploads its recording", async () => {
  const fixture = clientFixture();
  const audio = new Blob(["wav-a"]);
  fixture.record.audio_sha256 = await sha256(audio);
  const saved = await syncSession(fixture.client, { audio, record: fixture.record });
  assert.equal(saved.sync_state, "ready");
  assert.deepEqual(fixture.counts(), { uploads: 0, updates: 0 });
});

test("upload response loss completes only after verifying stored WAV bytes", async () => {
  const fixture = clientFixture({ state: "uploading" });
  const audio = new Blob(["wav-a"]);
  fixture.record.audio_sha256 = await sha256(audio);
  assert.equal((await syncSession(fixture.client, { audio, record: fixture.record })).sync_state, "ready");
  assert.deepEqual(fixture.counts(), { uploads: 1, updates: 1 });
  const corrupted = clientFixture({ state: "uploading", stored: new Blob(["wav-b"]) });
  corrupted.record.audio_sha256 = fixture.record.audio_sha256;
  await assert.rejects(syncSession(corrupted.client, { audio, record: corrupted.record }), /unggahan ulang/);
  assert.equal(corrupted.counts().updates, 0);
});

test("account changes cannot submit another owner's local outbox", async () => {
  const fixture = clientFixture({ owner: "user-b" });
  await assert.rejects(syncSession(fixture.client, { audio: new Blob(["wav-a"]), record: fixture.record }), /Masuk kembali/);
  assert.deepEqual(fixture.counts(), { uploads: 0, updates: 0 });
});
