import { useState } from 'react'
import type { EvidencePackOut } from '../api/types'
import { Badge } from './Badge'
import { Alert } from './Alert'
import { reviewStatusTone } from '../lib/status'
import { ReviewActions } from './ReviewActions'

interface EvidencePackViewProps {
  pack: EvidencePackOut
}

export function EvidencePackView({ pack }: EvidencePackViewProps) {
  const [reviewStatus, setReviewStatus] = useState(pack.review_status)

  return (
    <div className="space-y-4 rounded-md border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-wrap items-center gap-2">
        {pack.conflict_flagged && <Badge tone="danger">⚠ Conflict flagged</Badge>}
        {pack.is_fallback && <Badge tone="neutral">No evidence found</Badge>}
        <Badge tone={reviewStatusTone(reviewStatus)}>{reviewStatus.replaceAll('_', ' ')}</Badge>
      </div>

      <Alert variant="info">{pack.disclaimer}</Alert>

      <section>
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Research summary</h3>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{pack.research_summary}</p>
      </section>

      {(pack.relevant_rulings.length > 0 || pack.relevant_standards.length > 0) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {pack.relevant_rulings.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Relevant rulings</h3>
              <ul className="mt-1 list-inside list-disc text-sm text-slate-700 dark:text-slate-300">
                {pack.relevant_rulings.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </section>
          )}
          {pack.relevant_standards.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Relevant standards</h3>
              <ul className="mt-1 list-inside list-disc text-sm text-slate-700 dark:text-slate-300">
                {pack.relevant_standards.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {pack.key_evidence_excerpts.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Key evidence excerpts</h3>
          <ul className="mt-2 space-y-2">
            {pack.key_evidence_excerpts.map((ex, i) => (
              <li key={i} className="rounded border border-slate-200 p-2 text-sm dark:border-slate-800">
                <p className="text-slate-700 dark:text-slate-300">“{ex.excerpt}”</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {ex.citation.document_name} v{ex.citation.version}
                  {ex.citation.section_label ? ` — ${ex.citation.section_label}` : ''}
                  {ex.citation.page_number ? `, p.${ex.citation.page_number}` : ''}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {pack.comparison_table.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Comparison</h3>
          <div className="mt-2 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 dark:bg-slate-900">
                <tr>
                  {['Topic', 'Source A', 'Source B', 'Note'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium text-slate-500 dark:text-slate-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {pack.comparison_table.map((row, i) => {
                  const isConflict = row.note?.toUpperCase().includes('CONFLICT')
                  return (
                    <tr
                      key={i}
                      className={isConflict ? 'bg-red-50 dark:bg-red-950/40' : undefined}
                    >
                      <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{row.topic}</td>
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                        {row.source_a}
                        <div className="text-xs text-slate-400">{row.source_a_citation.document_name}</div>
                      </td>
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                        {row.source_b}
                        <div className="text-xs text-slate-400">{row.source_b_citation.document_name}</div>
                      </td>
                      <td className="px-3 py-2">
                        {row.note ? <Badge tone={isConflict ? 'danger' : 'success'}>{row.note}</Badge> : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {pack.open_issues.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Open issues</h3>
          <ul className="mt-1 list-inside list-disc text-sm text-slate-700 dark:text-slate-300">
            {pack.open_issues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </section>
      )}

      {pack.citations.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Citations</h3>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-500 dark:text-slate-400">
            {pack.citations.map((c, i) => (
              <li key={i}>
                {c.document_name} v{c.version}
                {c.section_label ? ` — ${c.section_label}` : ''}
                {c.page_number ? `, p.${c.page_number}` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}

      <ReviewActions pack={{ ...pack, review_status: reviewStatus }} onDecided={setReviewStatus} />
    </div>
  )
}
