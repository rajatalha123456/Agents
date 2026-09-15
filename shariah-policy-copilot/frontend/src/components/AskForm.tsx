import { useState, type FormEvent } from 'react'
import type { QueryFilters } from '../api/types'

interface AskFormProps {
  onSubmit: (question: string, filters: QueryFilters) => Promise<void> | void
  submitting: boolean
}

export function AskForm({ onSubmit, submitting }: AskFormProps) {
  const [question, setQuestion] = useState('')
  const [approvedOnly, setApprovedOnly] = useState(true)
  const [currentVersionOnly, setCurrentVersionOnly] = useState(true)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!question.trim()) return
    await onSubmit(question.trim(), {
      approved_only: approvedOnly,
      current_version_only: currentVersionOnly,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-slate-600 dark:text-slate-300">Question</span>
        <textarea
          aria-label="Question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="e.g. What is the late payment charge for Murabaha?"
          className="rounded border border-slate-300 px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800"
        />
      </label>

      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={approvedOnly} onChange={(e) => setApprovedOnly(e.target.checked)} />
          <span className="text-slate-600 dark:text-slate-300">Approved documents only</span>
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={currentVersionOnly}
            onChange={(e) => setCurrentVersionOnly(e.target.checked)}
          />
          <span className="text-slate-600 dark:text-slate-300">Current version only</span>
        </label>
      </div>

      <button
        type="submit"
        disabled={submitting || !question.trim()}
        className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? 'Researching…' : 'Ask'}
      </button>
    </form>
  )
}
