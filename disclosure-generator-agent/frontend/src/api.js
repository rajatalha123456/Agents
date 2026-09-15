const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";

class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request(path, options) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (networkError) {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
      null
    );
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // no/invalid JSON body -- leave body as null
  }

  if (!response.ok && response.status !== 422) {
    const detail = body?.detail || response.statusText;
    throw new ApiError(detail, response.status, body);
  }

  return { status: response.status, body };
}

export function checkHealth() {
  return request("/health", { method: "GET" });
}

export function signPayload({ runId, payload, signedAt }) {
  return request("/dev/sign", {
    method: "POST",
    body: JSON.stringify({
      run_id: runId,
      payload,
      signed_at: signedAt || undefined,
    }),
  });
}

export function generateDisclosure({ signedRun, language }) {
  return request("/disclosures/generate", {
    method: "POST",
    body: JSON.stringify({ signed_run: signedRun, language }),
  });
}

export { ApiError, API_BASE_URL };
