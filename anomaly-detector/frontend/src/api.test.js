import assert from 'node:assert/strict';
import { test } from 'node:test';
import { api } from './api.js';

test('large upload resumes after a lost chunk response and returns the saved analysis', async () => {
  const storage = new Map();
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  const file = new File([new Uint8Array(33 * 1024 ** 2)], 'bank.csv', { lastModified: 42 });
  let job = { id: 'upload-1', state: 'uploading', received: 0, size: file.size, rows_done: 0, batches_done: 0 };
  let lostResponse = false;
  const offsets = [];
  const json = (body) => new Response(JSON.stringify(body), { status: 200 });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    if (url.endsWith('upload-config')) return json({ max_file_bytes: 64 * 1024 ** 3, chunk_bytes: 8 * 1024 ** 2 });
    if (url.endsWith('/uploads')) return json(job);
    if (url.includes('/chunks?')) {
      const offset = Number(new URL(url, 'http://localhost').searchParams.get('offset'));
      assert.equal(offset, job.received);
      offsets.push(offset);
      job = { ...job, received: offset + options.body.get('file').size };
      if (!lostResponse) { lostResponse = true; throw new TypeError('Connection interrupted'); }
      return json(job);
    }
    if (url.endsWith('/complete')) { job = { ...job, state: 'completed', analysis_id: 'analysis-1' }; return json(job); }
    if (url.includes('/analyses/')) return json({ analysis_id: 'analysis-1', row_count: 120000 });
    return json(job);
  };
  try {
    const progress = [];
    const result = await api.analyzeFile(file, (state) => progress.push(state.received));
    assert.equal(result.row_count, 120000);
    assert.equal(offsets.length, 5);
    assert.equal(new Set(offsets).size, 5);
    assert.equal(progress.at(-1), file.size);
    assert.equal(api.pendingUpload(), null);
  } finally { globalThis.fetch = originalFetch; }
});

test('browser resumes an existing upload from its committed offset', async () => {
  const file = new File(['amount\n10\n'], 'resume.csv', { lastModified: 7 });
  let saved = JSON.stringify({ id: 'resume-1', fingerprint: `${file.name}:${file.size}:7` });
  globalThis.localStorage = {
    getItem: () => saved, setItem: (_, value) => { saved = value; }, removeItem: () => { saved = null; },
  };
  const originalFetch = globalThis.fetch;
  let job = { id: 'resume-1', state: 'uploading', received: 7, size: file.size };
  let created = false;
  globalThis.fetch = async (url, options = {}) => {
    let result = job;
    if (url.endsWith('upload-config')) result = { max_file_bytes: 0, chunk_bytes: 8 * 1024 ** 2 };
    if (url.endsWith('/uploads')) created = true;
    if (url.includes('/chunks?')) {
      assert.ok(url.endsWith('offset=7'));
      assert.equal(await options.body.get('file').text(), '10\n');
      job = { ...job, received: file.size };
      result = job;
    }
    if (url.endsWith('/complete')) { job = { ...job, state: 'completed', analysis_id: 'resume-1' }; result = job; }
    if (url.includes('/analyses/')) result = { analysis_id: 'resume-1' };
    return new Response(JSON.stringify(result));
  };
  try {
    assert.equal((await api.analyzeFile(file)).analysis_id, 'resume-1');
    assert.equal(created, false);
  } finally { globalThis.fetch = originalFetch; }
});
