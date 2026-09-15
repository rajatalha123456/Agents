import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, askQuestion, fetchDocuments, submitReviewDecision } from './client'
import type { Identity } from './client'

const identity: Identity = { userId: 'owais', role: 'shariah_researcher' }

function mockFetchOnce(response: Partial<Response> & { jsonBody?: unknown }) {
  const { jsonBody, ...rest } = response
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => jsonBody,
    ...rest,
  } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchDocuments', () => {
  it('sends Basic auth and role headers, and parses the JSON body', async () => {
    const fetchMock = mockFetchOnce({ jsonBody: [{ id: '1', document_name: 'Doc A' }] })

    const docs = await fetchDocuments(identity)

    expect(docs).toEqual([{ id: '1', document_name: 'Doc A' }])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/documents?current_only=true')
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toMatch(/^Basic /)
    expect(headers['X-User-Id']).toBe('owais')
    expect(headers['X-User-Role']).toBe('shariah_researcher')
  })
})

describe('askQuestion', () => {
  it('POSTs the question and filters as JSON', async () => {
    const fetchMock = mockFetchOnce({ jsonBody: { id: 'p1', review_status: 'human_review_required' } })

    await askQuestion(identity, 'What is the late payment charge?', {
      approved_only: true,
      current_version_only: true,
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/query/ask')
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    expect(body).toEqual({
      user_id: 'owais',
      question: 'What is the late payment charge?',
      filters: { approved_only: true, current_version_only: true },
    })
  })
})

describe('error handling', () => {
  it('throws an ApiError with the detail message on a non-OK response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        json: async () => ({ detail: 'Invalid username or password' }),
      } as Response),
    )

    await expect(fetchDocuments(identity)).rejects.toMatchObject(
      new ApiError(401, 'Invalid username or password'),
    )
  })

  it('submits an approve decision to /review/{id}', async () => {
    const fetchMock = mockFetchOnce({
      jsonBody: { id: 'p1', review_status: 'approved', reviewer_id: 'mufti', reviewed_at: '2026-01-01' },
    })

    const result = await submitReviewDecision(identity, 'p1', true)

    expect(result.review_status).toBe('approved')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('/review/p1')
    expect(JSON.parse(init.body as string)).toEqual({ approve: true })
  })
})
