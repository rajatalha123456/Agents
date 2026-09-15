import { useState } from 'react'
import { useIdentity } from '../context/IdentityContext'
import { submitReviewDecision, ApiError } from '../api/client'
import type { EvidencePackOut } from '../api/types'
import { Alert } from './Alert'

interface ReviewActionsProps {
  pack: EvidencePackOut
  onDecided: (reviewStatus: string) => void
}

export function ReviewActions({ pack, onDecided }: ReviewActionsProps) {
  const { identity } = useIdentity()
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (identity.role !== 'shariah_reviewer') return null
  if (pack.review_status !== 'human_review_required') return null

  async function decide(approve: boolean) {
    setPending(true)
    setError(null)
    try {
      const result = await submitReviewDecision(identity, pack.id, approve)
      onDecided(result.review_status)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit review decision.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-800">
      <p className="text-sm font-medium text-slate-700 dark:text-slate-200">Reviewer decision</p>
      {error && <Alert variant="error">{error}</Alert>}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={() => decide(true)}
          className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => decide(false)}
          className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
