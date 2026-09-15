import type { DocumentOut, EvidencePackOut, QueryFilters, Role } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
// Dev-only stub credentials — see app/utils/security.py (`admin`/`admin` hardcoded until real auth ships).
const BASIC_AUTH_USER = import.meta.env.VITE_BASIC_AUTH_USER ?? 'admin'
const BASIC_AUTH_PASS = import.meta.env.VITE_BASIC_AUTH_PASS ?? 'admin'

export interface Identity {
  userId: string
  role: Role
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

function authHeaders(identity: Identity): HeadersInit {
  return {
    Authorization: 'Basic ' + btoa(`${BASIC_AUTH_USER}:${BASIC_AUTH_PASS}`),
    'X-User-Id': identity.userId,
    'X-User-Role': identity.role,
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
    }
    return JSON.stringify(body)
  } catch {
    return response.statusText || `Request failed with status ${response.status}`
  }
}

async function request<T>(path: string, init: RequestInit, identity: Identity): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...authHeaders(identity),
      ...(init.headers ?? {}),
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function fetchDocuments(
  identity: Identity,
  params: { currentOnly?: boolean } = {},
): Promise<DocumentOut[]> {
  const query = new URLSearchParams()
  query.set('current_only', String(params.currentOnly ?? true))
  return request<DocumentOut[]>(`/documents?${query.toString()}`, { method: 'GET' }, identity)
}

export interface UploadDocumentInput {
  file: File
  document_name: string
  document_type: string
  version: string
  approval_status: string
  product_category?: string
  jurisdiction?: string
  approved_by?: string
  confidentiality_level: string
  supersedes_document_id?: string
}

export function uploadDocument(identity: Identity, input: UploadDocumentInput): Promise<DocumentOut> {
  const form = new FormData()
  form.set('file', input.file)
  form.set('document_name', input.document_name)
  form.set('document_type', input.document_type)
  form.set('version', input.version)
  form.set('approval_status', input.approval_status)
  form.set('confidentiality_level', input.confidentiality_level)
  if (input.product_category) form.set('product_category', input.product_category)
  if (input.jurisdiction) form.set('jurisdiction', input.jurisdiction)
  if (input.approved_by) form.set('approved_by', input.approved_by)
  if (input.supersedes_document_id) form.set('supersedes_document_id', input.supersedes_document_id)

  return request<DocumentOut>('/documents/upload', { method: 'POST', body: form }, identity)
}

export function askQuestion(
  identity: Identity,
  question: string,
  filters: QueryFilters,
): Promise<EvidencePackOut> {
  return request<EvidencePackOut>(
    '/query/ask',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: identity.userId, question, filters }),
    },
    identity,
  )
}

export interface ReviewDecisionResult {
  id: string
  review_status: string
  reviewer_id: string
  reviewed_at: string
}

export function submitReviewDecision(
  identity: Identity,
  evidencePackId: string,
  approve: boolean,
): Promise<ReviewDecisionResult> {
  return request<ReviewDecisionResult>(
    `/review/${evidencePackId}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approve }),
    },
    identity,
  )
}
