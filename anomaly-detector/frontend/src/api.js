const BASE = '/v1';

async function req(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const res = await fetch(BASE + path, { headers, ...opts });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw Object.assign(new Error(body.detail || `Request failed: ${res.status}`), { status: res.status });
  }
  return res.json();
}

// Multipart upload — no Content-Type header (the browser sets the
// multipart boundary itself; forcing application/json here breaks it).
async function reqForm(path, formData, signal) {
  const res = await fetch(BASE + path, { method: 'POST', body: formData, signal });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw Object.assign(new Error(body.detail || `Request failed: ${res.status}`), { status: res.status });
  }
  return res.json();
}

const PENDING_UPLOAD = 'anomaly.pending-upload';
function pendingUpload() {
  try { return JSON.parse(localStorage.getItem(PENDING_UPLOAD) || 'null'); } catch { return null; }
}
function rememberUpload(value) {
  try {
    if (value) localStorage.setItem(PENDING_UPLOAD, JSON.stringify(value));
    else localStorage.removeItem(PENDING_UPLOAD);
  } catch { /* Upload can continue without browser persistence. */ }
}
const delay = (ms, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) { reject(new DOMException('Paused', 'AbortError')); return; }
  const abort = () => { clearTimeout(timer); reject(new DOMException('Paused', 'AbortError')); };
  const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
  signal?.addEventListener('abort', abort, { once: true });
});

async function waitForUpload(id, onProgress, signal) {
  while (true) {
    const job = await req(`/anomaly/uploads/${id}`, { signal });
    onProgress(job);
    if (job.state === 'completed') {
      const result = await req(`/anomaly/analyses/${job.analysis_id}`, { signal });
      rememberUpload(null);
      return result;
    }
    if (['failed', 'cancelled', 'cancelling'].includes(job.state)) {
      throw new Error(job.error || 'Analysis cancelled.');
    }
    await delay(2000, signal);
  }
}

async function uploadLargeFile(file, onProgress, signal) {
  const config = await req('/anomaly/upload-config', { signal });
  if (config.max_file_bytes && file.size > config.max_file_bytes) {
    throw new Error('File exceeds this deployment’s configured upload capacity.');
  }
  const fingerprint = `${file.name}:${file.size}:${file.lastModified}`;
  const pending = pendingUpload();
  let job;
  if (pending && pending.fingerprint !== fingerprint) {
    const previous = await req(`/anomaly/uploads/${pending.id}`, { signal }).catch((error) => {
      if (error.status === 404) return null;
      throw error;
    });
    if (previous && !['completed', 'cancelled'].includes(previous.state)) {
      throw new Error('Resume or cancel the previous upload before choosing another large file.');
    }
  }
  if (pending?.fingerprint === fingerprint) {
    try { job = await req(`/anomaly/uploads/${pending.id}`, { signal }); }
    catch (error) { if (error.status !== 404) throw error; }
  }
  if (job && ['failed', 'cancelled'].includes(job.state)) {
    if (job.state === 'failed') await req(`/anomaly/uploads/${job.id}`, { method: 'DELETE', signal });
    job = null;
  }
  if (!job) {
    job = await req('/anomaly/uploads', { method: 'POST', body: JSON.stringify({ filename: file.name, size: file.size }), signal });
    rememberUpload({ id: job.id, fingerprint, filename: file.name });
  }
  onProgress(job);
  if (job.state === 'uploading') {
    while (job.received < file.size) {
      let uploaded = false;
      for (let attempt = 0; attempt < 3 && !uploaded; attempt += 1) {
        const form = new FormData();
        form.append('file', file.slice(job.received, job.received + config.chunk_bytes), 'chunk');
        try {
          job = await reqForm(`/anomaly/uploads/${job.id}/chunks?offset=${job.received}`, form, signal);
          uploaded = true;
        } catch (error) {
          if (signal?.aborted || (error.status && error.status < 500) || error.status === 507 || attempt === 2) throw error;
          await delay(1000 * (attempt + 1), signal);
          // The server may have committed a chunk before the response was lost.
          job = await req(`/anomaly/uploads/${job.id}`, { signal });
          if (job.received === file.size) uploaded = true;
        }
      }
      onProgress(job);
    }
    await req(`/anomaly/uploads/${job.id}/complete`, { method: 'POST', signal });
  }
  return waitForUpload(job.id, onProgress, signal);
}

export const api = {
  pendingUpload,
  uploadConfig: () => req('/anomaly/upload-config'),
  uploadStatus: (id) => req(`/anomaly/uploads/${id}`),
  waitForUpload,
  cancelUpload: async (id) => {
    const job = await req(`/anomaly/uploads/${id}`, { method: 'DELETE' });
    rememberUpload(null);
    return job;
  },
  analyzeFile: async (file, onProgress = () => {}, signal) => {
    if (file.size > 32 * 1024 ** 2 || pendingUpload()?.fingerprint === `${file.name}:${file.size}:${file.lastModified}`) {
      return uploadLargeFile(file, onProgress, signal);
    }
    const fd = new FormData();
    fd.append('file', file);
    try { return await reqForm('/anomaly/analyze-file', fd, signal); }
    catch (error) {
      if (error.status === 413) return uploadLargeFile(file, onProgress, signal);
      throw error;
    }
  },
  analyses: () => req('/anomaly/analyses'),
  analysis: (id) => req(`/anomaly/analyses/${id}`),
  explainAnomaly: (analysisId, anomalyId) => req(`/anomaly/analyses/${analysisId}/anomalies/${anomalyId}/explain`, {
    method: 'POST',
  }),
  chatAboutAnomaly: (analysisId, anomalyId, body) => req(`/anomaly/analyses/${analysisId}/anomalies/${anomalyId}/chat`, {
    method: 'POST',
    body: JSON.stringify(body),
  }),
};
