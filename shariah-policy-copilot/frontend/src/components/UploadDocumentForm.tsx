import { useState, type FormEvent } from 'react'
import { APPROVAL_STATUSES } from '../api/types'

export interface UploadFormValues {
  file: File
  document_name: string
  document_type: string
  version: string
  approval_status: string
  product_category: string
  jurisdiction: string
  confidentiality_level: string
}

interface UploadDocumentFormProps {
  onSubmit: (values: UploadFormValues) => Promise<void> | void
  submitting: boolean
}

const initialState = {
  document_name: '',
  document_type: '',
  version: '1.0',
  approval_status: 'draft',
  product_category: '',
  jurisdiction: '',
  confidentiality_level: 'internal',
}

export function UploadDocumentForm({ onSubmit, submitting }: UploadDocumentFormProps) {
  const [file, setFile] = useState<File | null>(null)
  const [values, setValues] = useState(initialState)
  const [validationError, setValidationError] = useState<string | null>(null)

  function update<K extends keyof typeof initialState>(key: K, value: (typeof initialState)[K]) {
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!file) {
      setValidationError('Please choose a file to upload.')
      return
    }
    if (!values.document_name.trim() || !values.document_type.trim()) {
      setValidationError('Document name and type are required.')
      return
    }
    setValidationError(null)
    await onSubmit({ file, ...values })
    setFile(null)
    setValues(initialState)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-md border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Upload a document</h3>

      {validationError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {validationError}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          <span className="text-slate-600 dark:text-slate-300">File (PDF / DOCX / TXT)</span>
          <input
            aria-label="File"
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-slate-700 dark:text-slate-200"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-600 dark:text-slate-300">Document name</span>
          <input
            aria-label="Document name"
            value={values.document_name}
            onChange={(e) => update('document_name', e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-600 dark:text-slate-300">Document type</span>
          <input
            aria-label="Document type"
            placeholder="ruling | fatwa | standard | policy | …"
            value={values.document_type}
            onChange={(e) => update('document_type', e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-600 dark:text-slate-300">Version</span>
          <input
            aria-label="Version"
            value={values.version}
            onChange={(e) => update('version', e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-600 dark:text-slate-300">Approval status</span>
          <select
            aria-label="Approval status"
            value={values.approval_status}
            onChange={(e) => update('approval_status', e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
          >
            {APPROVAL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-600 dark:text-slate-300">Product category</span>
          <input
            aria-label="Product category"
            value={values.product_category}
            onChange={(e) => update('product_category', e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-slate-600 dark:text-slate-300">Jurisdiction</span>
          <input
            aria-label="Jurisdiction"
            value={values.jurisdiction}
            onChange={(e) => update('jurisdiction', e.target.value)}
            className="rounded border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
          />
        </label>
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? 'Uploading…' : 'Upload'}
      </button>
    </form>
  )
}
