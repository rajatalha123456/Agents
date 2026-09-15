import { useCallback, useEffect, useState } from 'react'
import { fetchDocuments, uploadDocument, ApiError } from '../api/client'
import type { DocumentOut } from '../api/types'
import { useIdentity } from '../context/IdentityContext'
import { DocumentsTable } from '../components/DocumentsTable'
import { UploadDocumentForm, type UploadFormValues } from '../components/UploadDocumentForm'
import { Alert } from '../components/Alert'

export function DocumentsPage() {
  const { identity } = useIdentity()
  const [documents, setDocuments] = useState<DocumentOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const docs = await fetchDocuments(identity)
      setDocuments(docs)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load documents.')
    } finally {
      setLoading(false)
    }
  }, [identity])

  useEffect(() => {
    load()
  }, [load])

  async function handleUpload(values: UploadFormValues) {
    setUploading(true)
    setError(null)
    setUploadSuccess(null)
    try {
      const doc = await uploadDocument(identity, values)
      setUploadSuccess(`Ingested "${doc.document_name}" (v${doc.version}).`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to upload document.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-4">
      {error && <Alert variant="error">{error}</Alert>}
      {uploadSuccess && <Alert variant="success">{uploadSuccess}</Alert>}
      <DocumentsTable documents={documents} loading={loading} />
      <UploadDocumentForm onSubmit={handleUpload} submitting={uploading} />
    </div>
  )
}
