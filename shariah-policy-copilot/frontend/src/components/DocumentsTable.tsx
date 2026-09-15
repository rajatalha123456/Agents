import type { DocumentOut } from '../api/types'
import { Badge } from './Badge'
import { approvalStatusTone } from '../lib/status'

interface DocumentsTableProps {
  documents: DocumentOut[]
  loading: boolean
}

export function DocumentsTable({ documents, loading }: DocumentsTableProps) {
  if (loading) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">Loading documents…</p>
  }

  if (documents.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No documents ingested yet. Upload one below, or run{' '}
        <code className="rounded bg-slate-100 px-1 py-0.5 dark:bg-slate-800">
          python -m scripts.seed_sample_docs
        </code>
        .
      </p>
    )
  }

  return (
    <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
        <thead className="bg-slate-50 dark:bg-slate-900">
          <tr>
            {['Name', 'Type', 'Version', 'Status', 'Category', 'Jurisdiction'].map((h) => (
              <th key={h} className="px-3 py-2 text-left font-medium text-slate-500 dark:text-slate-400">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{doc.document_name}</td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{doc.document_type}</td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{doc.version}</td>
              <td className="px-3 py-2">
                <Badge tone={approvalStatusTone(doc.approval_status)}>
                  {doc.status_emoji} {doc.approval_status}
                </Badge>
              </td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{doc.product_category ?? '—'}</td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{doc.jurisdiction ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
