import type { ProblemDetails } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  problem: ProblemDetails | null;

  constructor(status: number, problem: ProblemDetails | null, message: string) {
    super(message);
    this.status = status;
    this.problem = problem;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  isFormData?: boolean;
  query?: Record<string, string | number | boolean | undefined>;
}

function buildQuery(query?: RequestOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined) params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, isFormData = false, query } = options;
  const url = `${path}${buildQuery(query)}`;

  const headers: Record<string, string> = {};
  if (!isFormData && body !== undefined) headers["Content-Type"] = "application/json";

  const resp = await fetch(`${BASE_URL}${url}`, {
    method,
    headers,
    body: isFormData ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!resp.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = await resp.json();
    } catch {
      // no JSON body
    }
    throw new ApiError(resp.status, problem, problem?.detail ?? resp.statusText);
  }

  if (resp.status === 204) return undefined as T;

  const contentType = resp.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await resp.json()) as T;
  }
  return (await resp.text()) as unknown as T;
}
