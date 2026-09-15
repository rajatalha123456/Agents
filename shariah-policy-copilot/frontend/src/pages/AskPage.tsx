import { useState } from 'react'
import { askQuestion, ApiError } from '../api/client'
import type { EvidencePackOut, QueryFilters } from '../api/types'
import { useIdentity } from '../context/IdentityContext'
import { AskForm } from '../components/AskForm'
import { EvidencePackView } from '../components/EvidencePackView'
import { Alert } from '../components/Alert'

export function AskPage() {
  const { identity } = useIdentity()
  const [pack, setPack] = useState<EvidencePackOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleAsk(question: string, filters: QueryFilters) {
    setSubmitting(true)
    setError(null)
    setPack(null)
    try {
      const result = await askQuestion(identity, question, filters)
      setPack(result)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to get an answer.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <AskForm onSubmit={handleAsk} submitting={submitting} />
      {error && <Alert variant="error">{error}</Alert>}
      {pack && <EvidencePackView pack={pack} />}
    </div>
  )
}
