const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export async function analyzeContract(file) {
  const formData = new FormData()
  formData.append('contract', file)

  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // ignore non-JSON error body
    }
    throw new Error(detail)
  }

  return res.json()
}
